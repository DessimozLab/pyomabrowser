from django.conf.urls import patterns, include, url

from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'pybrowser_dev.views.home', name='home'),
    # url(r'^blog/', include('blog.urls')),
    url(r'^oma/', include('oma.urls')),
)
