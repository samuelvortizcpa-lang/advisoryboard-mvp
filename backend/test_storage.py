"""Quick smoke test for Supabase Storage integration."""

import sys
from dotenv import load_dotenv

load_dotenv()

from app.services.storage_service import upload_file, download_file, delete_file

TEST_BYTES = b"Hello from AdvisoryBoard storage test!"
USER_ID = "test-user-000"
CLIENT_ID = "test-client-000"
FILE_ID = "test-file-000"
FILENAME = "test.txt"
CONTENT_TYPE = "text/plain"


def main():
    errors = 0

    # 1. Upload
    print("1. Upload ...", end=" ")
    try:
        path = upload_file(USER_ID, CLIENT_ID, FILE_ID, FILENAME, TEST_BYTES, CONTENT_TYPE)
        print(f"OK  (path={path})")
    except Exception as e:
        print(f"FAIL  ({e})")
        errors += 1
        sys.exit(1)

    # 2. Download + verify
    print("2. Download ...", end=" ")
    try:
        data = download_file(path)
        if data == TEST_BYTES:
            print("OK  (bytes match)")
        else:
            print(f"FAIL  (expected {len(TEST_BYTES)} bytes, got {len(data)})")
            errors += 1
    except Exception as e:
        print(f"FAIL  ({e})")
        errors += 1

    # 3. Delete
    print("3. Delete ...", end=" ")
    try:
        delete_file(path)
        print("OK")
    except Exception as e:
        print(f"FAIL  ({e})")
        errors += 1

    # 4. Verify deletion (download should fail)
    print("4. Verify deleted ...", end=" ")
    try:
        download_file(path)
        print("FAIL  (file still exists)")
        errors += 1
    except Exception:
        print("OK  (file gone)")

    print()
    if errors:
        print(f"FAILED ({errors} error(s))")
        sys.exit(1)
    else:
        print("ALL PASSED")


if __name__ == "__main__":
    main()
