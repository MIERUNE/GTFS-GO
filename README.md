# GTFS-GO

QGIS Plugin to extract GTFS-data as GeoJSON and render routes and stops on the Map.

<img src='./doc_imgs/img_01.gif'>

## Usage

## Custom Datalist

### Datalist-Json Spec

## Translation

1. edit to `gtfs_go.pro` and add `GTFSGO_lang_encoding.ts` inside the `TRANSLATION` variable
2. cd i18n
3. generate the translation files with `pylupdate5 ../gtfs_go.pro` on debian you have to install pylupdate with `apt install pyqt5-dev-tools`
4. edit the newly generated file GTFSGO_lang.ts to contain the new translations
5. generate qm file with `lrelease GTFSGO_lang_encoding.ts`

