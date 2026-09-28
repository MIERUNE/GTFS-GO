import os
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests
from qgis.core import (
    QgsApplication,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingMultiStepFeedback,
    QgsTask,
)
from qgis.PyQt.QtCore import Qt

import i18n

# seconds; (connect, read) timeout for downloading a GTFS zip
DOWNLOAD_TIMEOUT_SEC = (10, 300)
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


@dataclass
class AlgorithmJob:
    algorithm: QgsProcessingAlgorithm
    # parameters except INPUT and outputs
    parameters: dict
    # list of (output parameter name, file name, layer name, style function)
    outputs: list


@dataclass
class FeedResult:
    group: str
    # holds temporary layers until they are taken
    context: QgsProcessingContext
    # list of (layer name, output id, style function)
    outputs: list = field(default_factory=list)


class GTFSGoTask(QgsTask):
    """Download GTFS feeds and run algorithms on them in background

    Layers are not touched here: results are handed to on_finished, which is
    called on the main thread.
    """

    def __init__(
        self,
        feed_infos: list,
        jobs: list,
        output_root: str,
        temp_dir: str,
        on_finished: Callable[["GTFSGoTask", bool], None],
    ):
        super().__init__(i18n.tr("Loading GTFS data"), QgsTask.Flag.CanCancel)
        self.feed_infos = feed_infos
        self.jobs = jobs
        self.output_root = output_root
        self.temp_dir = temp_dir
        self.on_finished = on_finished
        self.feedback = QgsProcessingFeedback()
        # emitted in the worker thread, which has no event loop for queued calls
        self.feedback.progressChanged.connect(
            self.setProgress, Qt.ConnectionType.DirectConnection
        )
        self.results: list = []
        self.errors: list = []

    def cancel(self):
        self.feedback.cancel()
        super().cancel()

    def run(self) -> bool:
        try:
            self.run_feeds()
        except Exception as e:
            self.errors.append(str(e))
            return False
        return not self.isCanceled()

    def finished(self, result: bool):
        self.on_finished(self, result)

    def run_feeds(self):
        # steps for each feed: downloading if needed, and running each algorithm
        feed_steps = [
            int(feed_info["path"].startswith("http")) + len(self.jobs)
            for feed_info in self.feed_infos
        ]
        progress = QgsProcessingMultiStepFeedback(sum(feed_steps), self.feedback)

        for i, feed_info in enumerate(self.feed_infos):
            if self.isCanceled():
                return
            step = sum(feed_steps[:i])
            path = feed_info["path"]
            if path.startswith("http"):
                progress.setCurrentStep(step)
                step += 1
                path = self.download_zip(path, progress)
                if path is None:
                    continue

            # without output directory, outputs are temporary (memory) layers
            output_dir = None
            if self.output_root:
                output_dir = os.path.join(self.output_root, feed_info["dir"])
                os.makedirs(output_dir, exist_ok=True)

            # created in this thread, as algorithms create temporary layers in it
            context = QgsProcessingContext()
            result = FeedResult(feed_info["group"], context)
            for job in self.jobs:
                progress.setCurrentStep(step)
                step += 1
                results = self.run_algorithm(
                    job.algorithm,
                    {
                        **job.parameters,
                        "INPUT": path,
                        **{
                            name: destination(output_dir, filename)
                            for name, filename, _, _ in job.outputs
                        },
                    },
                    context,
                    progress,
                )
                if results is None:
                    break
                result.outputs += [
                    (layer_name, results[name], style_func)
                    for name, _, layer_name, style_func in job.outputs
                ]
            else:
                # hand temporary layers over to the main thread
                context.pushToThread(QgsApplication.instance().thread())
                self.results.append(result)

    def download_zip(self, url: str, feedback: QgsProcessingFeedback) -> Optional[str]:
        download_path = os.path.join(self.temp_dir, str(uuid.uuid4()) + ".zip")
        with requests.get(url, timeout=DOWNLOAD_TIMEOUT_SEC, stream=True) as response:
            if response.status_code != 200:
                self.errors.append(
                    i18n.tr("Failed to download GTFS data from the URL: ") + url
                )
                return None
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            with open(download_path, mode="wb") as f:
                for chunk in response.iter_content(DOWNLOAD_CHUNK_SIZE):
                    if self.isCanceled():
                        return None
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        feedback.setProgress(100 * downloaded / total)
        return download_path

    def run_algorithm(
        self,
        algorithm: QgsProcessingAlgorithm,
        parameters: dict,
        context: QgsProcessingContext,
        progress: QgsProcessingFeedback,
    ) -> Optional[dict]:
        """
        Returns:
            results of the algorithm, None if failed or canceled
        """
        alg = algorithm.create()
        # own feedback to get the log of this algorithm only
        feedback = QgsProcessingFeedback()
        feedback.progressChanged.connect(progress.setProgress)
        # canceled on the main thread, so call directly instead of queueing
        self.feedback.canceled.connect(
            feedback.cancel, Qt.ConnectionType.DirectConnection
        )
        if self.isCanceled():
            return None
        ok, message = alg.checkParameterValues(parameters, context)
        results = None
        if ok:
            results, ok = alg.run(parameters, context, feedback)
            message = feedback.textLog()
        if feedback.isCanceled():
            return None
        if not ok:
            self.errors.append(alg.displayName() + ": " + message)
            return None
        return results


def destination(output_dir: Optional[str], filename: str) -> str:
    if output_dir is None:
        return "memory:"
    return os.path.join(output_dir, filename)
