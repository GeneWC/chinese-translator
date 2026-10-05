import os
import re
from pathlib import Path

from .resources import package_path


class OfflineTranslator:
    """Argos packages/tokenizers with their native CTranslate2 CPU backend.

    Punctuation supplies sentence boundaries for these short screen selections.
    Avoid Argos' optional SBD models, which otherwise download during a lookup.
    """

    def __init__(self, root: Path):
        self.root = root
        self.engines = {}

    def translate(self, text: str, code="zh") -> str:
        if code not in self.engines:
            # Scope Argos-owned caches to the app, before importing its settings.
            for key, value in {
                "XDG_DATA_HOME": self.root / "cache", "XDG_CACHE_HOME": self.root / "cache",
                "XDG_CONFIG_HOME": self.root / "config", "ARGOS_PACKAGES_DIR": self.root / "models",
            }.items():
                os.environ[key] = str(value)
            import ctranslate2
            from argostranslate.package import Package
            path = package_path(self.root, code)
            package = Package(path)
            engine = ctranslate2.Translator(str(path / "model"), device="cpu", compute_type="int8",
                                           inter_threads=1, intra_threads=4)
            self.engines[code] = package, engine
        package, engine = self.engines[code]
        sentences = [s.strip() for s in re.findall(r"[^。！？!?\n]+[。！？!?]*|[。！？!?]+", text) if s.strip()]
        tokenized = []
        for sentence in sentences:
            tokens = package.tokenizer.encode(sentence)
            tokenized.extend(tokens[i:i+200] for i in range(0, len(tokens), 200))
        if not tokenized:
            return ""
        prefix = [[package.target_prefix]]*len(tokenized) if package.target_prefix else None
        batches = engine.translate_batch(tokenized, target_prefix=prefix, beam_size=4,
            replace_unknowns=True, max_batch_size=32, batch_type="tokens", length_penalty=.2,
            max_input_length=256, max_decoding_length=512)
        translated = []
        for batch in batches:
            value = package.tokenizer.decode(batch.hypotheses[0]).strip()
            if package.target_prefix and value.startswith(package.target_prefix):
                value = value[len(package.target_prefix):].strip()
            translated.append(value)
        return " ".join(translated)
