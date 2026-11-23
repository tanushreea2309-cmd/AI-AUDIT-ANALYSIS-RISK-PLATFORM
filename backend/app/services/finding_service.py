from typing import Any, cast

from app.core.supabase_client import supabase


class FindingService:

    @staticmethod
    def get_all_findings():
        findings_response = (
            supabase
            .table("findings")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        findings = cast(list[dict[str, Any]], findings_response.data or [])

        analyses_response = (
            supabase
            .table("analyses")
            .select("*")
            .execute()
        )
        analyses = cast(list[dict[str, Any]], analyses_response.data or [])

        datasets_response = (
            supabase
            .table("datasets")
            .select("*")
            .execute()
        )
        datasets = cast(list[dict[str, Any]], datasets_response.data or [])

        clients_response = (
            supabase
            .table("clients")
            .select("*")
            .execute()
        )
        clients = cast(list[dict[str, Any]], clients_response.data or [])

        analysis_map = {
            str(analysis.get("id")): analysis
            for analysis in analyses
            if analysis.get("id")
        }

        dataset_map = {
            str(dataset.get("id")): dataset
            for dataset in datasets
            if dataset.get("id")
        }

        client_map = {
            str(client.get("id")): client
            for client in clients
            if client.get("id")
        }

        for finding in findings:
            analysis_id = str(finding.get("analysis_id") or "")
            analysis = analysis_map.get(analysis_id)

            if not analysis:
                finding["analyses"] = None
                continue

            dataset_id = str(analysis.get("dataset_id") or "")
            dataset = dataset_map.get(dataset_id)

            if dataset:
                client_id = str(dataset.get("client_id") or "")
                client = client_map.get(client_id)
                dataset["clients"] = client

            analysis["datasets"] = dataset
            finding["analyses"] = analysis

        return findings

    @staticmethod
    def get_finding(finding_id: str):
        findings = FindingService.get_all_findings()

        for finding in findings:
            if str(finding.get("id")) == finding_id:
                return finding

        return None