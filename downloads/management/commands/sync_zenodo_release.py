"""
Sync OMA Browser download files from Zenodo into the local downloads database.

Single-record mode (primary use):
    python manage.py sync_zenodo_release <record_id> <release_name> [options]

Concept-record mode — sync ALL versions from one concept DOI at once:
    python manage.py sync_zenodo_release <concept_id> --concept [options]

Merge mode — add files from a second Zenodo record (e.g. OMAmer) into
existing releases without overwriting their metadata:
    python manage.py sync_zenodo_release <omamer_record_id> <release_name> --merge
    python manage.py sync_zenodo_release <omamer_concept_id> --concept --merge

Examples:
    # Sync a single release and mark it as latest
    python manage.py sync_zenodo_release 20816928 All.Mar2026 --set-latest

    # Bulk-sync every OMA Browser release from the concept record
    python manage.py sync_zenodo_release 20816667 --concept

    # Add OMAmer files into the same releases (different Zenodo concept)
    python manage.py sync_zenodo_release 99999999 --concept --merge

    # Draft/restricted records require a token
    python manage.py sync_zenodo_release 20816667 --concept --token $ZENODO_TOKEN
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from downloads.models import Release, ReleaseFile

logger = logging.getLogger(__name__)

ZENODO_API = "https://zenodo.org/api"


class Command(BaseCommand):
    help = 'Sync file lists from Zenodo into the downloads database'

    def add_arguments(self, parser):
        parser.add_argument('record_id', help='Zenodo record ID or concept record ID (with --concept)')
        parser.add_argument(
            'release_name',
            nargs='?',
            help='Release name, e.g. All.Mar2026 (derived from Zenodo metadata when using --concept)',
        )
        parser.add_argument(
            '--concept',
            action='store_true',
            help='Treat record_id as a concept/parent record and sync all its versions',
        )
        parser.add_argument(
            '--merge',
            action='store_true',
            help=(
                'Add files to existing releases without overwriting their metadata. '
                'Use when adding files from a second Zenodo record (e.g. OMAmer) '
                'that share the same release names.'
            ),
        )
        parser.add_argument(
            '--set-latest',
            action='store_true',
            help='Mark this release (or the newest version in --concept mode) as latest',
        )
        parser.add_argument(
            '--release-name-prefix',
            metavar='PREFIX',
            help=(
                'Prepend PREFIX. to version names that contain no dot. '
                'Use when a Zenodo record stores bare versions like "Mar2026" '
                'that should map to existing releases like "All.Mar2026". '
                'Also sets release_group to PREFIX when creating new releases.'
            ),
        )
        parser.add_argument(
            '--release-date',
            help='Release date as YYYY-MM-DD (single-record mode only; defaults to Zenodo publication_date)',
        )
        parser.add_argument(
            '--token',
            help='Zenodo API token (required for draft or restricted records)',
        )

    def handle(self, *args, **options):
        token = options.get('token')
        if options['concept']:
            self._sync_concept(options['record_id'], options, token)
        else:
            if not options['release_name']:
                raise CommandError('release_name is required in single-record mode (omit only with --concept)')
            self._sync_single(options['record_id'], options['release_name'], options, token)

    # ------------------------------------------------------------------ #
    # Concept-record mode                                                  #
    # ------------------------------------------------------------------ #

    def _sync_concept(self, concept_id, options, token):
        self.stdout.write(f"Fetching all versions of concept record {concept_id}…")
        versions = self._fetch_all_versions(concept_id, token)
        if not versions:
            raise CommandError("No published versions found for this concept record")

        self.stdout.write(f"Found {len(versions)} version(s).")

        prefix = options.get('release_name_prefix') or ''

        latest_id = None
        for v in versions:
            rels = v.get('metadata', {}).get('relations', {})
            version_rels = rels.get('version', []) if isinstance(rels, dict) else []
            if any(r.get('is_last') for r in version_rels):
                latest_id = v['id']

        for v in versions:
            record_id = str(v['id'])
            release_name = v.get('metadata', {}).get('version', '')
            if not release_name:
                self.stderr.write(f"  Skipping record {record_id}: no 'version' field in metadata")
                continue

            # Normalize bare version names like "Mar2026" → "All.Mar2026"
            if prefix and '.' not in release_name:
                release_name = f"{prefix}.{release_name}"

            is_latest = (options['set_latest'] and record_id == str(latest_id))
            pub_date_str = v.get('metadata', {}).get('publication_date', '')

            self.stdout.write(f"\n— {release_name} (record {record_id})")
            self._sync_record(
                record_id=record_id,
                release_name=release_name,
                release_group=prefix or release_name.split('.')[0],
                record=v,
                pub_date_str=pub_date_str,
                release_date_override=None,
                is_latest=is_latest,
                merge=options['merge'],
                token=token,
            )

    def _fetch_all_versions(self, concept_id, token):
        """Return list of all published version records for a concept record."""
        # Unauthenticated requests are limited to 25 results per page.
        page_size = 100 if token else 25
        results = []
        page = 1
        while True:
            params = urllib.parse.urlencode({
                'q': f'conceptrecid:{concept_id}',
                'all_versions': '1',
                'sort': 'mostrecent',
                'size': page_size,
                'page': page,
            })
            data = self._fetch_json(f"{ZENODO_API}/records?{params}", token)
            hits = data.get('hits', {}).get('hits', [])
            results.extend(hits)
            if len(results) >= data.get('hits', {}).get('total', 0):
                break
            page += 1
        return results

    # ------------------------------------------------------------------ #
    # Single-record mode                                                   #
    # ------------------------------------------------------------------ #

    def _sync_single(self, record_id, release_name, options, token):
        self.stdout.write(f"Fetching Zenodo record {record_id}…")
        try:
            record = self._fetch_json(f"{ZENODO_API}/records/{record_id}", token)
        except urllib.error.HTTPError as exc:
            raise CommandError(f"Zenodo API returned {exc.code}: {exc.reason}") from exc

        prefix = options.get('release_name_prefix') or ''
        if prefix and '.' not in release_name:
            release_name = f"{prefix}.{release_name}"

        pub_date_str = record.get('metadata', {}).get('publication_date', '')[:10]
        self._sync_record(
            record_id=record_id,
            release_name=release_name,
            release_group=prefix or release_name.split('.')[0],
            record=record,
            pub_date_str=pub_date_str,
            release_date_override=options.get('release_date'),
            is_latest=options['set_latest'],
            merge=options['merge'],
            token=token,
        )

    # ------------------------------------------------------------------ #
    # Core sync logic (shared)                                             #
    # ------------------------------------------------------------------ #

    def _sync_record(self, record_id, release_name, release_group, record, pub_date_str,
                     release_date_override, is_latest, merge, token):
        # Resolve release date
        if release_date_override:
            release_date = datetime.strptime(release_date_override, '%Y-%m-%d').date()
        elif pub_date_str:
            release_date = datetime.strptime(pub_date_str[:10], '%Y-%m-%d').date()
        else:
            raise CommandError(f"No publication date for record {record_id}; pass --release-date")

        doi = record.get('metadata', {}).get('doi', record.get('doi', ''))

        if merge:
            # In merge mode: find existing release or create it, but don't overwrite metadata
            release, created = Release.objects.get_or_create(
                name=release_name,
                defaults={
                    'zenodo_record_id': record_id,
                    'zenodo_doi': doi,
                    'release_date': release_date,
                    'release_group': release_group,
                    'is_latest': is_latest,
                },
            )
            if created:
                self.stdout.write(f"  Created release: {release_name}")
            else:
                self.stdout.write(f"  Merging into existing release: {release_name}")
                if is_latest and not release.is_latest:
                    release.is_latest = True
                    release.save()
        else:
            release, created = Release.objects.update_or_create(
                name=release_name,
                defaults={
                    'zenodo_record_id': record_id,
                    'zenodo_doi': doi,
                    'release_date': release_date,
                    'release_group': release_group,
                    'is_latest': is_latest,
                },
            )
            self.stdout.write(f"  {'Created' if created else 'Updated'} release: {release_name}")

        # Sync files
        files = self._get_files(record_id, record, token)
        if not files:
            self.stderr.write(f"  Warning: no files found in record {record_id}")
            return

        synced = 0
        for entry in files:
            filename = entry.get('key', entry.get('filename', ''))
            if not filename:
                continue
            url = f"https://zenodo.org/records/{record_id}/files/{filename}?download=1"
            ReleaseFile.objects.update_or_create(
                release=release,
                filename=filename,
                defaults={
                    'download_url': url,
                    'size': entry.get('size', 0),
                    'checksum': entry.get('checksum', ''),
                    'source_type': ReleaseFile.SOURCE_ZENODO,
                    'source_record_id': str(record_id),
                },
            )
            synced += 1
            self.stdout.write(f"    {filename} ({self._fmt_size(entry.get('size', 0))})")

        suffix = ' [latest]' if is_latest else ''
        suffix += ' [merged]' if merge else ''
        self.stdout.write(self.style.SUCCESS(f"  Synced {synced} file(s){suffix}"))

    # ------------------------------------------------------------------ #
    # Zenodo API helpers                                                   #
    # ------------------------------------------------------------------ #

    def _fetch_json(self, url, token=None):
        req = urllib.request.Request(url, headers={'Accept': 'application/json'})
        if token:
            req.add_header('Authorization', f'Bearer {token}')
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    def _get_files(self, record_id, record, token):
        """Return list of file dicts with at least 'key' and 'size'."""
        try:
            data = self._fetch_json(f"{ZENODO_API}/records/{record_id}/files", token)
            if 'entries' in data:
                entries = data['entries']
                return list(entries.values()) if isinstance(entries, dict) else entries
        except (urllib.error.HTTPError, KeyError):
            pass
        return record.get('files', [])

    @staticmethod
    def _fmt_size(n):
        for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
            if n < 1024:
                return f"{n:.0f} {unit}"
            n /= 1024
        return f"{n:.1f} PB"
