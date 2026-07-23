"""
Sync OMA Browser download files from a Backblaze B2 bucket into the local downloads database.

Requires the b2sdk package: pip install b2sdk

Single-release mode:
    python manage.py sync_b2_release <bucket> --release-name All.Mar2026 [options]

Prefix-scan mode — derive release name from each sub-folder in the bucket:
    python manage.py sync_b2_release <bucket> --scan-releases [options]

Examples:
    # Sync all files from a release folder in the bucket, using a Cloudflare-fronted URL
    python manage.py sync_b2_release oma-downloads \\
        --release-name All.Mar2026 \\
        --prefix All.Mar2026/ \\
        --base-url https://downloads.omabrowser.org \\
        --set-latest

    # Auto-discover all release folders (each top-level folder = one release)
    python manage.py sync_b2_release oma-downloads \\
        --scan-releases \\
        --base-url https://downloads.omabrowser.org

Credentials:
    Pass --key-id and --key, or set B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY env vars.
"""

import datetime
import logging
import os

from django.core.management.base import BaseCommand, CommandError

from downloads.models import Release, ReleaseFile

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync file lists from a Backblaze B2 bucket into the downloads database'

    def add_arguments(self, parser):
        parser.add_argument('bucket', help='B2 bucket name')
        parser.add_argument(
            '--release-name',
            metavar='NAME',
            help='Release name (e.g. All.Mar2026). Required unless --scan-releases is used.',
        )
        parser.add_argument(
            '--prefix',
            metavar='PATH',
            default='',
            help=(
                'Path prefix within the bucket to list files under '
                '(e.g. "All.Mar2026/"). Defaults to --release-name + "/" '
                'when --release-name is given.'
            ),
        )
        parser.add_argument(
            '--scan-releases',
            action='store_true',
            help=(
                'Discover releases by listing top-level "folders" in the bucket. '
                'Each folder name is used as the release name.'
            ),
        )
        parser.add_argument(
            '--base-url',
            metavar='URL',
            help=(
                'Base URL for constructing download links '
                '(e.g. https://downloads.omabrowser.org). '
                'The full B2 file path is appended: {base_url}/{b2_path}. '
                'If omitted, the native B2 download URL is used instead.'
            ),
        )
        parser.add_argument(
            '--release-group',
            default='',
            metavar='GROUP',
            help='Release group (default: derived from release name before the first dot).',
        )
        parser.add_argument(
            '--release-date',
            metavar='YYYY-MM-DD',
            help='Release date (default: today).',
        )
        parser.add_argument(
            '--set-latest',
            action='store_true',
            help='Mark this release as latest within its group.',
        )
        parser.add_argument(
            '--merge',
            action='store_true',
            help='Add files to an existing release without overwriting its metadata.',
        )
        parser.add_argument(
            '--key-id',
            metavar='KEY_ID',
            default='',
            help='B2 application key ID (default: B2_APPLICATION_KEY_ID env var).',
        )
        parser.add_argument(
            '--key',
            metavar='SECRET',
            default='',
            help='B2 application key (default: B2_APPLICATION_KEY env var).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be synced without touching the DB.',
        )

    def handle(self, *args, **options):
        try:
            from b2sdk.v2 import B2Api, InMemoryAccountInfo
        except ImportError:
            raise CommandError(
                'b2sdk is not installed. Run: pip install b2sdk'
            )

        key_id = options['key_id'] or os.environ.get('B2_APPLICATION_KEY_ID', '')
        key = options['key'] or os.environ.get('B2_APPLICATION_KEY', '')
        if not key_id or not key:
            raise CommandError(
                'B2 credentials required. Pass --key-id / --key or set '
                'B2_APPLICATION_KEY_ID / B2_APPLICATION_KEY environment variables.'
            )

        info = InMemoryAccountInfo()
        api = B2Api(info)
        try:
            api.authorize_account('production', key_id, key)
        except Exception as exc:
            raise CommandError(f'B2 authentication failed: {exc}') from exc

        bucket_name = options['bucket']
        try:
            bucket = api.get_bucket_by_name(bucket_name)
        except Exception as exc:
            raise CommandError(f'Cannot access bucket {bucket_name!r}: {exc}') from exc

        if options['scan_releases']:
            self._scan_releases(api, bucket, options)
        else:
            if not options['release_name']:
                raise CommandError(
                    '--release-name is required unless --scan-releases is used.'
                )
            prefix = options['prefix'] or f"{options['release_name']}/"
            self._sync_release(api, bucket, options['release_name'], prefix, options)

    # ------------------------------------------------------------------ #
    # Scan mode                                                            #
    # ------------------------------------------------------------------ #

    def _scan_releases(self, api, bucket, options):
        """List top-level "folders" in the bucket; treat each as a release."""
        self.stdout.write(f"Scanning bucket {bucket.name!r} for release folders…")
        folders = set()
        for file_info, folder_name in bucket.ls(recursive=False):
            if folder_name:
                folders.add(folder_name.rstrip('/'))

        if not folders:
            raise CommandError('No top-level folders found in bucket. Nothing to sync.')

        self.stdout.write(f"Found {len(folders)} release folder(s): {', '.join(sorted(folders))}")
        for folder in sorted(folders):
            prefix = folder + '/'
            release_name = folder
            self.stdout.write(f"\n— {release_name}")
            self._sync_release(api, bucket, release_name, prefix, options)

    # ------------------------------------------------------------------ #
    # Core sync logic                                                      #
    # ------------------------------------------------------------------ #

    def _sync_release(self, api, bucket, release_name, prefix, options):
        base_url = (options['base_url'] or '').rstrip('/')
        dry_run = options['dry_run']

        release_group = options['release_group'] or release_name.split('.')[0]

        if options['release_date']:
            try:
                release_date = datetime.date.fromisoformat(options['release_date'])
            except ValueError as exc:
                raise CommandError(f'Invalid --release-date: {exc}') from exc
        else:
            release_date = datetime.date.today()

        self.stdout.write(
            f"  Listing files under prefix {prefix!r} in {bucket.name!r}…"
        )
        files = list(bucket.ls(folder_to_list=prefix, recursive=True, latest_only=True))
        # Filter to files only (ls returns (FileVersion, folder_name) tuples)
        file_entries = [(fv, fn) for fv, fn in files if fn is None]

        if not file_entries:
            self.stderr.write(f"  Warning: no files found under prefix {prefix!r}")
            return

        self.stdout.write(f"  Found {len(file_entries)} file(s).")

        if not dry_run:
            source_bucket_ref = f"b2:{bucket.name}"
            if options['merge']:
                release, created = Release.objects.get_or_create(
                    name=release_name,
                    defaults={
                        'release_group': release_group,
                        'release_date': release_date,
                        'is_latest': options['set_latest'],
                    },
                )
                if created:
                    self.stdout.write(f"  Created release: {release_name}")
                else:
                    self.stdout.write(f"  Merging into existing release: {release_name}")
                    if options['set_latest'] and not release.is_latest:
                        release.is_latest = True
                        release.save()
            else:
                release, created = Release.objects.update_or_create(
                    name=release_name,
                    defaults={
                        'release_group': release_group,
                        'release_date': release_date,
                        'is_latest': options['set_latest'],
                    },
                )
                self.stdout.write(f"  {'Created' if created else 'Updated'} release: {release_name}")

        synced = 0
        for file_version, _ in file_entries:
            b2_path = file_version.file_name  # e.g. "All.Mar2026/OmaServer.h5"
            filename = b2_path[len(prefix):].lstrip('/')  # strip prefix → "OmaServer.h5"
            if not filename:
                continue

            if base_url:
                download_url = f"{base_url}/{b2_path}"
            else:
                download_url = api.get_download_url_for_file_name(bucket.name, b2_path)

            try:
                sha1 = file_version.get_content_sha1()
                checksum = f"sha1:{sha1}"
            except Exception:
                checksum = 'sha1:none'
                self.stdout.write(f"    Warning: no SHA1 checksum for {filename}")

            size = getattr(file_version, 'size', 0) or 0

            self.stdout.write(
                f"    {'[dry-run] ' if dry_run else ''}{filename} "
                f"({self._fmt_size(size)}) -> {download_url}"
            )

            if not dry_run:
                ReleaseFile.objects.update_or_create(
                    release=release,
                    filename=filename,
                    defaults={
                        'download_url': download_url,
                        'size': size,
                        'checksum': checksum,
                        'source_type': ReleaseFile.SOURCE_B2,
                        'source_record_id': source_bucket_ref,
                    },
                )
                synced += 1

        suffix = ' [latest]' if options['set_latest'] else ''
        suffix += ' [merged]' if options['merge'] else ''
        if dry_run:
            self.stdout.write(f"  [dry-run] Would sync {len(file_entries)} file(s){suffix}")
        else:
            self.stdout.write(self.style.SUCCESS(f"  Synced {synced} file(s){suffix}"))

    @staticmethod
    def _fmt_size(n):
        for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
            if n < 1024:
                return f"{n:.0f} {unit}"
            n /= 1024
        return f"{n:.1f} PB"
