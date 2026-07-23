from django.contrib import admin
from django.db.models import Count

from .models import DownloadEvent, Release, ReleaseFile


class ReleaseFileInline(admin.TabularInline):
    model = ReleaseFile
    readonly_fields = ('filename', 'size_display', 'download_count', 'source_type', 'download_url', 'checksum')
    fields = ('filename', 'size_display', 'download_count', 'source_type', 'download_url', 'checksum')
    extra = 0
    can_delete = False
    show_change_link = False

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _download_count=Count('download_events')
        )

    @admin.display(description='Size')
    def size_display(self, obj):
        n = obj.size
        for unit in ('B', 'KB', 'MB', 'GB'):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"

    @admin.display(description='Downloads')
    def download_count(self, obj):
        return obj._download_count


@admin.register(Release)
class ReleaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'release_group', 'zenodo_record_id', 'release_date', 'is_latest', 'file_count', 'total_downloads')
    list_filter = ('release_group', 'is_latest')
    readonly_fields = ('zenodo_doi',)
    inlines = [ReleaseFileInline]
    actions = ['mark_as_latest']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _file_count=Count('files', distinct=True),
            _total_downloads=Count('files__download_events'),
        )

    @admin.display(description='Files', ordering='_file_count')
    def file_count(self, obj):
        return obj._file_count

    @admin.display(description='Total Downloads', ordering='_total_downloads')
    def total_downloads(self, obj):
        return obj._total_downloads

    @admin.action(description='Mark selected release as latest (within its group)')
    def mark_as_latest(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one release to mark as latest.", level='error')
            return
        release = queryset.get()
        release.is_latest = True
        release.save()
        self.message_user(request, f"{release.name} is now the latest release in group '{release.release_group}'.")
