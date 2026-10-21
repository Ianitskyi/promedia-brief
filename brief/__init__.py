"""BRIEF news pipeline.

RSS -> normalize -> dedupe -> cluster -> classify -> score -> script draft
-> fact checks -> editorial approval -> TTS -> audio assembly -> publish.

Every stage is a plain function over JSON-serialisable dicts so that each
intermediate result can be stored in the repository and inspected by editors.
"""

__version__ = "0.2.0"
