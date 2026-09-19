from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.core.errors import NotFoundError
from backend.app.repositories.scene_repo import SceneRepository
from backend.app.runtime.scene_importer import infer_scene_id, import_scene
from backend.app.runtime.scene_layout import ensure_scene_layout, validate_scene_layout
from backend.app.schemas.graph import GraphEdge, GraphNode, SceneGraphResponse
from backend.app.schemas.scene import SceneImportRequest, SceneLayoutValidation, ScenePublishRequest, SceneRead, SceneVersionRead


class SceneService:
    def __init__(self, db: Session) -> None:
        self.repo = SceneRepository(db)

    def list_scenes(self) -> list[SceneRead]:
        return [
            SceneRead(
                id=scene.id,
                name=scene.name,
                domain=scene.domain,
                description=scene.description,
                created_at=scene.created_at,
            )
            for scene in self.repo.list_scenes()
        ]

    def get_scene(self, scene_id: str) -> SceneRead:
        scene = self.repo.get_scene(scene_id)
        if scene is None:
            raise NotFoundError(f"Scene not found: {scene_id}")
        return SceneRead(
            id=scene.id,
            name=scene.name,
            domain=scene.domain,
            description=scene.description,
            created_at=scene.created_at,
        )

    def list_versions(self, scene_id: str) -> list[SceneVersionRead]:
        if self.repo.get_scene(scene_id) is None:
            raise NotFoundError(f"Scene not found: {scene_id}")
        return [
            SceneVersionRead(
                id=version.id,
                scene_id=version.scene_id,
                version=version.version,
                graph_summary=version.graph_summary,
                created_at=version.created_at,
            )
            for version in self.repo.list_versions(scene_id)
        ]

    def import_scene(self, request: SceneImportRequest) -> SceneVersionRead:
        scene_id = request.scene_id or None
        resolved_id = scene_id or infer_scene_id(request.source_json)
        next_version = self.repo.next_version_number(resolved_id)
        imported = import_scene(
            request.source_json,
            scene_id=scene_id,
            version=next_version,
            description=request.description,
        )
        saved = self.repo.save_imported_scene(imported)
        return SceneVersionRead(
            id=saved.id,
            scene_id=saved.scene_id,
            version=saved.version,
            graph_summary=saved.graph_summary,
            created_at=saved.created_at,
        )

    def get_graph(self, scene_version_id: str) -> SceneGraphResponse:
        version = self.repo.get_version(scene_version_id)
        if version is None:
            raise NotFoundError(f"Scene version not found: {scene_version_id}")
        nodes = self.repo.version_nodes(scene_version_id)
        edges = self.repo.version_edges(scene_version_id)
        return SceneGraphResponse(
            scene_version_id=scene_version_id,
            source_json=ensure_scene_layout(version.source_json),
            nodes=[
                GraphNode(
                    id=node.node_key,
                    node_type=node.node_type,
                    semantic_type=node.semantic_type,
                    properties=node.properties,
                )
                for node in nodes
            ],
            edges=[
                GraphEdge(
                    source_id=edge.source_key,
                    target_id=edge.target_key,
                    relation=edge.relation,
                    properties=edge.properties,
                )
                for edge in edges
            ],
        )

    def validate_layout(self, scene_version_id: str, source_json: dict) -> SceneLayoutValidation:
        if self.repo.get_version(scene_version_id) is None:
            raise NotFoundError(f"Scene version not found: {scene_version_id}")
        issues = validate_scene_layout(source_json)
        return SceneLayoutValidation(valid=not issues, issues=issues)

    def publish_layout(self, scene_version_id: str, request: ScenePublishRequest) -> SceneVersionRead:
        base_version = self.repo.get_version(scene_version_id)
        if base_version is None:
            raise NotFoundError(f"Scene version not found: {scene_version_id}")
        issues = validate_scene_layout(request.source_json)
        if issues:
            raise ValueError("; ".join(issues))
        return self.import_scene(
            SceneImportRequest(
                scene_id=base_version.scene_id,
                source_json=request.source_json,
                description=request.description,
            )
        )
