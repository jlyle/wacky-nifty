Wacky Vault v2 duplicate support package

Drop-in files:
- app.py
- templates/index.html
- templates/card_detail.html

Adds:
- duplicate_count support
- duplicates-only filter
- duplicate count editing in spreadsheet and gallery
- duplicate total stat
- exports including duplicate counts

Install:
cp app.py app.py.bak
cp templates/index.html templates/index.html.bak
cp templates/card_detail.html templates/card_detail.html.bak

cp /path/to/app.py .
cp /path/to/index.html templates/
cp /path/to/card_detail.html templates/

./run.sh
