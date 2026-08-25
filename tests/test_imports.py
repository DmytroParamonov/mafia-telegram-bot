def test_application_modules_import() -> None:
    import app.handlers  # noqa: F401
    import app.main  # noqa: F401
    import app.service  # noqa: F401
