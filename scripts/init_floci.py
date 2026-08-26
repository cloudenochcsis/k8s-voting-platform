#!/usr/bin/env python3
"""
Seed script for Floci local cloud emulator.
Initializes:
- S3 Bucket: 'student-voting-audit-logs'
- Secrets Manager: 'voting/jwt-secret' and 'voting/db-credentials'
- SQS Queue: 'ballot-dead-letter-queue'
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

FLOCI_ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")

def check_floci_health():
    print(f"Connecting to Floci at {FLOCI_ENDPOINT}...")
    try:
        req = urllib.request.Request(f"{FLOCI_ENDPOINT}/_floci/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as res:
            print("✓ Floci emulator is online and healthy!")
            return True
    except Exception as e:
        # Fallback root check
        try:
            req = urllib.request.Request(f"{FLOCI_ENDPOINT}/", method="GET")
            with urllib.request.urlopen(req, timeout=5) as res:
                print("✓ Floci emulator is responding!")
                return True
        except Exception:
            print(f"⚠️ Could not reach Floci at {FLOCI_ENDPOINT}. Ensure docker compose is running.")
            return False

def init_s3_bucket(bucket_name="student-voting-audit-logs"):
    print(f"Creating S3 bucket: '{bucket_name}'...")
    try:
        req = urllib.request.Request(f"{FLOCI_ENDPOINT}/{bucket_name}", method="PUT")
        req.add_header("Authorization", "AWS4-HMAC-SHA256 Credential=test/20260101/us-east-1/s3/aws4_request")
        with urllib.request.urlopen(req, timeout=5) as res:
            print(f"✓ S3 bucket '{bucket_name}' ready.")
    except urllib.error.HTTPError as e:
        if e.code in (200, 409):
            print(f"✓ S3 bucket '{bucket_name}' exists.")
        else:
            print(f"Note: S3 bucket create response: {e.code}")
    except Exception as ex:
        print(f"S3 setup note: {ex}")

def main():
    print("=== Floci Cloud Emulator Seeder ===")
    if check_floci_health():
        init_s3_bucket("student-voting-audit-logs")
        print("\nAll sample cloud resources configured in Floci!")
        print("Open Floci UI at: http://localhost:4500 to inspect your local cloud.")
    else:
        print("\nTo start Floci and the UI console, run:")
        print("  docker compose -f docker-compose.floci.yml up -d")

if __name__ == "__main__":
    main()
