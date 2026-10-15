"""Prints each failed or errored test in a JUnit XML report as a GitHub
annotation, so failures are readable without signing in to GitHub."""
import sys
import xml.etree.ElementTree as ET

path = sys.argv[1] if len(sys.argv) > 1 else "junit.xml"
for case in ET.parse(path).iter("testcase"):
    for bad in list(case.iter("failure")) + list(case.iter("error")):
        text = f"{bad.get('message') or ''} {(bad.text or '')[-1500:]}"
        text = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::error title={case.get('classname')}.{case.get('name')}::{text}")
