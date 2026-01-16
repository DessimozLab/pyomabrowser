from django.apps import AppConfig


class OmaConfig(AppConfig):
    name = 'oma'
    
    def ready(self):
        # Monkeypatch pyoma HOG.hog_id to be defensive: if underlying
        # _hog data is missing, return None instead of raising.
        try:
            import pyoma.browser.models as _models

            def _safe_hog_id(self):
                try:
                    if getattr(self, '_hog', None) is None:
                        return None
                    val = self._hog.get('ID')
                    return val.decode() if val is not None else None
                except Exception:
                    return None

            _models.HOG.hog_id = property(_safe_hog_id)

            # Make HOG objects evaluate to False in boolean contexts when
            # their underlying `_hog` data is missing. This lets templates
            # use `{% if most_specific_hog %}` safely.
            def _hog_bool(self):
                try:
                    return getattr(self, '_hog', None) is not None
                except Exception:
                    return False

            # Only set __bool__ if not already present to avoid overriding
            # user code unexpectedly.
            if not hasattr(_models.HOG, '__bool__'):
                _models.HOG.__bool__ = _hog_bool
        except Exception:
            # If pyoma is not importable (e.g., in certain test contexts), skip
            pass
