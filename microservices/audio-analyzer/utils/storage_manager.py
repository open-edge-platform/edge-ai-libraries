import os
import json, csv
from threading import Thread
from typing import Union, List, Dict, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class StorageManager:
    @staticmethod
    def _ensure_dir(path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)

    @staticmethod
    def _prepare_json_data(path: str, data: dict, append: bool) -> list:
        if append and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    if isinstance(existing, list):
                        existing.append(data)
                        return existing
                    return [existing, data]
            except json.JSONDecodeError:
                return [data]
        return [data]  # Always return list

    @staticmethod
    def _write(path: str, data: Union[str, dict], append: bool):
        StorageManager._ensure_dir(path)

        if isinstance(data, dict):
            data = StorageManager._prepare_json_data(path, data, append)
            # Always overwrite to maintain valid JSON
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            mode = 'a' if append else 'w'
            with open(path, mode, encoding="utf-8") as f:
                f.write(data)

    @staticmethod
    def save(path: str, data: Union[str, dict], append: bool = False):
        StorageManager._write(path, data, append)

    @staticmethod
    def save_async(path: str, data: Union[str, dict], append: bool = False):
        Thread(target=StorageManager._write, args=(path, data, append)).start()
        
    @staticmethod
    def save_csv(path: str, data: dict, headers: List[str], append: bool = True):
        StorageManager._ensure_dir(path)
        # Write headers only if file doesn't exist or append==False
        if not os.path.exists(path) or not append:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()

        with open(path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writerow(data)

    @staticmethod
    def update_csv(path: str, new_data: Dict[str, Union[str, int, float]]):
        StorageManager._ensure_dir(path)

        rows = []
        headers = set(new_data.keys())

        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                for row in rows:
                    headers.update(row.keys())

        if rows:
            rows[0].update(new_data)
        else:
            rows = [new_data]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(headers))
            writer.writeheader()
            writer.writerows(rows)
            
    @staticmethod
    def read_performance_metrics(project_location: str, project_name: str, session_id: str) -> dict:
        metrics_csv = os.path.join(project_location, project_name, session_id, "performance_metrics.csv")

        if not os.path.exists(metrics_csv):
            return {}

        def convert_value(val):
            try:
                f = float(val)
                return int(f) if f.is_integer() else f
            except Exception:
                return val

        with open(metrics_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                return {}

            latest = rows[-1]
            nested_data = {}

            for key, value in latest.items():
                val = convert_value(value)
                if "." in key:
                    group, subkey = key.split(".", 1)
                    if group not in nested_data:
                        nested_data[group] = {}
                    nested_data[group][subkey] = val
                else:
                    nested_data[key] = val

            return nested_data

    @staticmethod
    def read_text_file(path: str | Path) -> str | None:
        """
        Reads a text file and returns its content as a string.
        Returns None if the file is empty or contains only whitespace.
        """
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            raise
        except Exception as e:
            raise RuntimeError(f"Error reading file {path}: {e}")
