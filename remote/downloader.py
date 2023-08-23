import updates, sys

try:
    version = sys.argv[1:][0]

except Exception:
    print("Could not detect version wanted. Usuage: python3 downloader.py <version>")

    raise SystemExit

updates = updates.update_manager(toltec=False)
updates.get_update(version)
