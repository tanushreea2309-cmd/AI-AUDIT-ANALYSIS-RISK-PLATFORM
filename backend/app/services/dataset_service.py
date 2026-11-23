import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pandas as pd
from fastapi import HTTPException

from app.core.supabase_client import supabase
from app.services.validation_service import ValidationService
from app.services.schema_mapping_service import SchemaMappingService


BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def clean_for_json(value: Any):
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if isinstance(value, dict):
        return {key: clean_for_json(val) for key, val in value.items()}

    if isinstance(value, list):
        return [clean_for_json(item) for item in value]

    return value


class DatasetService:

    @staticmethod
    def process_upload(client_id: str, uploaded_file):
        filename = uploaded_file.filename

        if not filename:
            raise HTTPException(status_code=400, detail="No file selected.")

        extension = filename.split(".")[-1].lower()
        allowed_types = ["csv", "xlsx", "json"]

        if extension not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Only CSV, XLSX and JSON files are supported."
            )

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_filename = f"{timestamp}_{filename}"
        file_path = UPLOAD_DIR / safe_filename

        with open(file_path, "wb") as buffer:
            buffer.write(uploaded_file.file.read())

        if extension == "csv":
            dataframe = pd.read_csv(
                file_path,
                sep=None,
                engine="python",
                encoding="utf-8-sig"
            )

        elif extension == "xlsx":
            dataframe = pd.read_excel(file_path)

        elif extension == "json":
            with open(file_path, "r", encoding="utf-8-sig") as file:
                data = json.load(file)

            if isinstance(data, dict):
                if "data" in data:
                    data = data["data"]
                elif "transactions" in data:
                    data = data["transactions"]
                else:
                    data = [data]

            dataframe = pd.DataFrame(data)

        else:
            raise HTTPException(status_code=400, detail="Unsupported file type.")

        validation = ValidationService.validate_dataframe(dataframe)

        mapping = SchemaMappingService.generate_mapping(
            dataframe.columns.tolist()
        )

        dataset_payload = {
            "client_id": client_id,
            "dataset_name": filename,
            "file_type": extension,
            "file_path": str(file_path),
            "total_records": len(dataframe),
            "total_columns": len(dataframe.columns),
            "upload_status": validation["status"],
        }

        response = (
            supabase
            .table("datasets")
            .insert(dataset_payload)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to save dataset metadata."
            )

        dataset = cast(dict[str, Any], response.data[0])

        preview = (
            dataframe
            .head(5)
            .astype(object)
            .where(pd.notnull(dataframe.head(5)), None)
            .to_dict(orient="records")
        )

        return clean_for_json(
            {
                "dataset": dataset,
                "preview": preview,
                "validation": validation,
                "mapping": mapping,
            }
        )

    @staticmethod
    def get_all_datasets():
        response = (
            supabase
            .table("datasets")
            .select("*, clients(*)")
            .order("upload_date", desc=True)
            .execute()
        )

        return response.data or []

    @staticmethod
    def get_dataset(dataset_id: str):
        response = (
            supabase
            .table("datasets")
            .select("*, clients(*)")
            .eq("id", dataset_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="Dataset not found.")

        return cast(dict[str, Any], response.data[0])

    @staticmethod
    def delete_dataset(dataset_id: str):
        dataset = cast(dict[str, Any], DatasetService.get_dataset(dataset_id))
        file_path = str(dataset.get("file_path") or "")

        response = (
            supabase
            .table("datasets")
            .delete()
            .eq("id", dataset_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to delete dataset."
            )

        if file_path:
            path = Path(file_path)

            if path.exists():
                path.unlink()

        return {
            "message": "Dataset deleted successfully.",
            "dataset_id": dataset_id,
        }

    @staticmethod
    def cleanup_old_datasets(days: int = 30):
        cutoff_date = datetime.now() - timedelta(days=days)

        old_response = (
            supabase
            .table("datasets")
            .select("*")
            .lt("upload_date", cutoff_date.isoformat())
            .execute()
        )

        old_datasets = old_response.data or []
        deleted_count = 0

        for dataset_raw in old_datasets:
            dataset = cast(dict[str, Any], dataset_raw)

            dataset_id = str(dataset.get("id") or "")
            file_path = str(dataset.get("file_path") or "")

            if dataset_id:
                (
                    supabase
                    .table("datasets")
                    .delete()
                    .eq("id", dataset_id)
                    .execute()
                )

                deleted_count += 1

            if file_path:
                path = Path(file_path)

                if path.exists():
                    path.unlink()

        return {
            "message": f"Deleted {deleted_count} dataset(s) older than {days} days.",
            "deleted_count": deleted_count,
        }