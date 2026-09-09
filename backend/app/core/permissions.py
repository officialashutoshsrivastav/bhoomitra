from __future__ import annotations

from typing import Dict, List, Set


class P:
    DOCUMENT_READ = "document.read"
    DOCUMENT_CREATE = "document.create"
    DOCUMENT_UPDATE = "document.update"
    DOCUMENT_DELETE = "document.delete"
    DOCUMENT_PUBLISH = "document.publish"
    DOCUMENT_REVIEW = "document.review"

    DATASET_READ = "dataset.read"
    DATASET_UPLOAD = "dataset.upload"
    DATASET_UPDATE = "dataset.update"
    DATASET_DELETE = "dataset.delete"
    DATASET_APPROVE = "dataset.approve"

    RESEARCH_CREATE = "research.create"
    RESEARCH_MANAGE = "research.manage"
    RESEARCH_PUBLISH = "research.publish"

    POLICY_READ = "policy.read"
    POLICY_MANAGE = "policy.manage"

    GIS_VIEW = "gis.view"
    GIS_MANAGE = "gis.manage"
    GIS_ANALYZE = "gis.analyze"

    RS_VIEW = "remote_sensing.view"
    RS_MANAGE = "remote_sensing.manage"

    ANALYTICS_RUN = "analytics.run"
    ANALYTICS_MANAGE_MODELS = "analytics.manage_models"

    SIMULATION_CREATE = "simulation.create"
    SIMULATION_RUN = "simulation.run"
    SIMULATION_APPROVE = "simulation.approve"

    AI_QUERY = "ai.query"
    EVIDENCE_READ = "evidence.read"
    SEARCH_USE = "search.use"

    WORKSPACE_CREATE = "workspace.create"
    WORKSPACE_MANAGE = "workspace.manage"

    INNOVATION_CREATE = "innovation.create"
    INNOVATION_SUBMIT = "innovation.submit"
    INNOVATION_EVALUATE = "innovation.evaluate"
    INNOVATION_MANAGE = "innovation.manage"

    REPORT_GENERATE = "report.generate"
    DASHBOARD_VIEW = "dashboard.view"
    DASHBOARD_NATIONAL = "dashboard.national"

    INTEGRATION_MANAGE = "integration.manage"
    NOTIFICATION_READ = "notification.read"

    ADMIN_MANAGE_USERS = "admin.manage_users"
    ADMIN_MANAGE_ROLES = "admin.manage_roles"
    ADMIN_MANAGE_ORGS = "admin.manage_organizations"
    ADMIN_MANAGE_CONFIG = "admin.manage_config"
    ADMIN_APPROVALS = "admin.approvals"
    AUDIT_READ = "audit.read"


ALL_PERMISSIONS: List[str] = sorted({v for k, v in vars(P).items() if not k.startswith("_") and isinstance(v, str)})

PERMISSION_DESCRIPTIONS: Dict[str, str] = {
    P.DOCUMENT_READ: "View documents and metadata",
    P.DOCUMENT_CREATE: "Upload new documents",
    P.DOCUMENT_UPDATE: "Update document metadata and versions",
    P.DOCUMENT_DELETE: "Archive or delete documents",
    P.DOCUMENT_PUBLISH: "Publish documents to the repository",
    P.DOCUMENT_REVIEW: "Review documents submitted for approval",
    P.DATASET_READ: "Browse dataset catalogue",
    P.DATASET_UPLOAD: "Upload datasets",
    P.DATASET_UPDATE: "Update dataset metadata",
    P.DATASET_DELETE: "Archive datasets",
    P.DATASET_APPROVE: "Approve datasets for publication",
    P.RESEARCH_CREATE: "Create research projects",
    P.RESEARCH_MANAGE: "Manage research projects",
    P.RESEARCH_PUBLISH: "Publish research outputs",
    P.POLICY_READ: "View policies and indicators",
    P.POLICY_MANAGE: "Manage policies and indicators",
    P.GIS_VIEW: "View GIS layers",
    P.GIS_MANAGE: "Manage GIS layers and boundaries",
    P.GIS_ANALYZE: "Run spatial analysis",
    P.RS_VIEW: "View remote sensing products",
    P.RS_MANAGE: "Manage remote sensing scenes",
    P.ANALYTICS_RUN: "Run analytics",
    P.ANALYTICS_MANAGE_MODELS: "Register and version analytical models",
    P.SIMULATION_CREATE: "Create policy scenarios",
    P.SIMULATION_RUN: "Run simulations",
    P.SIMULATION_APPROVE: "Approve simulation results",
    P.AI_QUERY: "Use the AI research assistant",
    P.EVIDENCE_READ: "Inspect evidence traces",
    P.SEARCH_USE: "Use global search",
    P.WORKSPACE_CREATE: "Create collaborative workspaces",
    P.WORKSPACE_MANAGE: "Manage any workspace",
    P.INNOVATION_CREATE: "Create innovation challenges",
    P.INNOVATION_SUBMIT: "Submit proposals",
    P.INNOVATION_EVALUATE: "Evaluate submissions",
    P.INNOVATION_MANAGE: "Manage innovation programmes",
    P.REPORT_GENERATE: "Generate reports",
    P.DASHBOARD_VIEW: "View dashboards",
    P.DASHBOARD_NATIONAL: "View national overview",
    P.INTEGRATION_MANAGE: "Configure external integrations",
    P.NOTIFICATION_READ: "Read notifications",
    P.ADMIN_MANAGE_USERS: "Manage users",
    P.ADMIN_MANAGE_ROLES: "Manage roles and permissions",
    P.ADMIN_MANAGE_ORGS: "Manage organizations",
    P.ADMIN_MANAGE_CONFIG: "Manage system configuration",
    P.ADMIN_APPROVALS: "Process approval queues",
    P.AUDIT_READ: "Read audit logs",
}


class Roles:
    SUPER_ADMIN = "super_administrator"
    PLATFORM_ADMIN = "platform_administrator"
    GOVERNMENT_OFFICIAL = "government_official"
    POLICY_MAKER = "policy_maker"
    RESEARCHER = "researcher"
    ACADEMIC = "academic_user"
    RESEARCH_ORG = "research_organization_user"
    GIS_ANALYST = "gis_analyst"
    DATA_ANALYST = "data_analyst"
    PROJECT_MANAGER = "project_manager"
    INNOVATION_EVALUATOR = "innovation_evaluator"
    EXPERT = "expert_industry_user"
    PUBLIC = "public_user"


ROLE_LABELS: Dict[str, str] = {
    Roles.SUPER_ADMIN: "Super Administrator",
    Roles.PLATFORM_ADMIN: "Platform Administrator",
    Roles.GOVERNMENT_OFFICIAL: "Government Official",
    Roles.POLICY_MAKER: "Policy Maker",
    Roles.RESEARCHER: "Researcher",
    Roles.ACADEMIC: "Academic User",
    Roles.RESEARCH_ORG: "Research Organization User",
    Roles.GIS_ANALYST: "GIS Analyst",
    Roles.DATA_ANALYST: "Data Analyst",
    Roles.PROJECT_MANAGER: "Project Manager",
    Roles.INNOVATION_EVALUATOR: "Innovation Evaluator",
    Roles.EXPERT: "Expert / Industry User",
    Roles.PUBLIC: "Public User",
}

_PUBLIC: Set[str] = {P.DOCUMENT_READ, P.DATASET_READ, P.POLICY_READ, P.GIS_VIEW, P.SEARCH_USE, P.DASHBOARD_VIEW, P.NOTIFICATION_READ, P.INNOVATION_SUBMIT, P.EVIDENCE_READ, P.RS_VIEW}
_RESEARCH: Set[str] = _PUBLIC | {P.DOCUMENT_CREATE, P.DOCUMENT_UPDATE, P.DATASET_UPLOAD, P.DATASET_UPDATE, P.RESEARCH_CREATE, P.RESEARCH_MANAGE, P.AI_QUERY, P.ANALYTICS_RUN, P.SIMULATION_CREATE, P.SIMULATION_RUN, P.WORKSPACE_CREATE, P.REPORT_GENERATE, P.GIS_ANALYZE}
_ANALYST: Set[str] = _RESEARCH | {P.ANALYTICS_MANAGE_MODELS, P.RS_MANAGE}
_GIS: Set[str] = _RESEARCH | {P.GIS_MANAGE, P.RS_MANAGE}
_POLICY: Set[str] = _RESEARCH | {P.POLICY_MANAGE, P.SIMULATION_APPROVE, P.DASHBOARD_NATIONAL, P.DOCUMENT_REVIEW}
_GOV: Set[str] = _POLICY | {P.DOCUMENT_PUBLISH, P.DATASET_APPROVE, P.RESEARCH_PUBLISH, P.ADMIN_APPROVALS}
_PM: Set[str] = _RESEARCH | {P.WORKSPACE_MANAGE, P.INNOVATION_CREATE, P.INNOVATION_MANAGE, P.DOCUMENT_REVIEW}
_EVAL: Set[str] = _PUBLIC | {P.INNOVATION_EVALUATE, P.AI_QUERY}
_PLATFORM_ADMIN: Set[str] = set(ALL_PERMISSIONS) - {P.ADMIN_MANAGE_ROLES}

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    Roles.SUPER_ADMIN: set(ALL_PERMISSIONS),
    Roles.PLATFORM_ADMIN: _PLATFORM_ADMIN,
    Roles.GOVERNMENT_OFFICIAL: _GOV,
    Roles.POLICY_MAKER: _POLICY,
    Roles.RESEARCHER: _RESEARCH,
    Roles.ACADEMIC: _RESEARCH,
    Roles.RESEARCH_ORG: _RESEARCH | {P.RESEARCH_PUBLISH},
    Roles.GIS_ANALYST: _GIS,
    Roles.DATA_ANALYST: _ANALYST,
    Roles.PROJECT_MANAGER: _PM,
    Roles.INNOVATION_EVALUATOR: _EVAL,
    Roles.EXPERT: _PUBLIC | {P.AI_QUERY, P.INNOVATION_SUBMIT, P.WORKSPACE_CREATE},
    Roles.PUBLIC: _PUBLIC,
}

ALL_ROLES: List[str] = list(ROLE_PERMISSIONS.keys())
