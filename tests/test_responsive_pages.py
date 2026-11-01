import pytest
from streamlit.testing.v1 import AppTest
import glob
import os

pages_to_test = [
    "dashboard.py",
    "pages/1_⚾_MLB.py",
    "pages/2_🏈_NFL.py",
    "pages/3_⚽_Futbol.py",
    "pages/4_🏀_NBA.py",
    "pages/5_📊_Rendimiento.py",
]

# Add calibration page dynamically
calib_pages = glob.glob("pages/*Calib*.py")
if calib_pages:
    pages_to_test.append(calib_pages[0])

@pytest.mark.parametrize("page_file", pages_to_test)
def test_page_renders_without_errors(page_file):
    assert os.path.exists(page_file), f"Page file {page_file} does not exist"
    app = AppTest.from_file(page_file, default_timeout=30)
    app.run()
    assert not app.exception, f"Exception occurred while rendering {page_file}: {app.exception}"

