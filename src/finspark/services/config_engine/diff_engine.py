"""Configuration diff engine - compares two configurations and identifies changes."""

from typing import Any

from finspark.schemas.configurations import ConfigDiffItem, ConfigDiffResponse


class ConfigDiffEngine:
    """Compares two configurations and produces a structured diff."""

    BREAKING_PATHS = {
        "auth.type",
        "base_url",
        "version",
        "endpoints",
    }

    def compare(
        self,
        config_a: dict[str, Any],
        config_b: dict[str, Any],
        config_a_id: str = "a",
        config_b_id: str = "b",
    ) -> ConfigDiffResponse:
        """Compare two configurations and return structured diff."""
        diffs: list[ConfigDiffItem] = []
        self._diff_recursive(config_a, config_b, "", diffs)

        breaking = sum(1 for d in diffs if d.is_breaking)

        return ConfigDiffResponse(
            config_a_id=config_a_id,
            config_b_id=config_b_id,
            total_changes=len(diffs),
            breaking_changes=breaking,
            diffs=diffs,
        )

    def _diff_recursive(
        self,
        a: Any,
        b: Any,
        path: str,
        diffs: list[ConfigDiffItem],
    ) -> None:
        if isinstance(a, dict) and isinstance(b, dict):
            all_keys = set(a.keys()) | set(b.keys())
            for key in sorted(all_keys):
                child_path = f"{path}.{key}" if path else key
                if key not in a:
                    diffs.append(
                        ConfigDiffItem(
                            path=child_path,
                            change_type="added",
                            new_value=b[key],
                            is_breaking=self._is_breaking(child_path),
                        )
                    )
                elif key not in b:
                    diffs.append(
                        ConfigDiffItem(
                            path=child_path,
                            change_type="removed",
                            old_value=a[key],
                            is_breaking=self._is_breaking(child_path),
                        )
                    )
                else:
                    self._diff_recursive(a[key], b[key], child_path, diffs)

        elif isinstance(a, list) and isinstance(b, list):
            max_len = max(len(a), len(b))
            for i in range(max_len):
                child_path = f"{path}[{i}]"
                if i >= len(a):
                    diffs.append(
                        ConfigDiffItem(
                            path=child_path,
                            change_type="added",
                            new_value=b[i],
                            is_breaking=self._is_breaking(path),
                        )
                    )
                elif i >= len(b):
                    diffs.append(
                        ConfigDiffItem(
                            path=child_path,
                            change_type="removed",
                            old_value=a[i],
                            is_breaking=self._is_breaking(path),
                        )
                    )
                else:
                    self._diff_recursive(a[i], b[i], child_path, diffs)

        elif a != b:
            diffs.append(
                ConfigDiffItem(
                    path=path,
                    change_type="modified",
                    old_value=a,
                    new_value=b,
                    is_breaking=self._is_breaking(path),
                )
            )

    def _is_breaking(self, path: str) -> bool:
        """Check if a change at this path is a breaking change."""
        return any(path.startswith(bp) or path == bp for bp in self.BREAKING_PATHS)
