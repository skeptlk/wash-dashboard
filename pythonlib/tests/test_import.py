"""Verify that the package imports correctly."""


def test_import_package():
    import enginewash

    assert hasattr(enginewash, "WashCalculator")
    assert hasattr(enginewash, "WashConfig")
    assert hasattr(enginewash, "GWFM")
    assert hasattr(enginewash, "DEGT")
    assert hasattr(enginewash, "EGTHDM")


def test_import_all_exports():
    from enginewash import __all__

    import enginewash

    for name in __all__:
        assert hasattr(enginewash, name), f"Missing export: {name}"
