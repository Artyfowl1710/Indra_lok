from setuptools import setup

setup(
    name="indra-tools",
    version="1.0.0",
    description="INDRA 100% Offline Unified Document Generation Suite",
    author="INDRA Dev Team",
    packages=["indra_tools"],
    package_dir={"indra_tools": "."},
    entry_points={
        "console_scripts": [
            "indra-tools=indra_tools.cli:main",
            "indra-pdf=indra_tools.pdf:main",
            "indra-pptx=indra_tools.pptx:main",
            "indra-xlsx=indra_tools.xlsx:main",
            "indra-docx=indra_tools.docx:main",
        ],
    },
)

