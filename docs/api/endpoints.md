# realtime-novel API 端点清单

- **Title**: realtime-novel API
- **Version**: 0.4.0
- **OpenAPI Version**: 3.1.0
- **总端点数**: 14

## actions

### `PATCH /api/projects/{project_id}/base`

**摘要**: Update Base

**说明**: 改 7 件基座 — 薄路由，调 update_base tool（v0.4.1 落库）

**operationId**: `update_base_api_projects__project_id__base_patch`

**Parameters**:
- [✓] `project_id` (path, string): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### `POST /api/projects/{project_id}/image`

**摘要**: Generate Image

**说明**: 生成主立绘 — 薄路由，调 generate_image tool（v0.4.1 落库）

**operationId**: `generate_image_api_projects__project_id__image_post`

**Parameters**:
- [✓] `project_id` (path, string): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### `POST /api/projects/{project_id}/interventions`

**摘要**: Submit Intervention

**说明**: 提交剧情干预（v0.4.1 落库）

**operationId**: `submit_intervention_api_projects__project_id__interventions_post`

**Parameters**:
- [✓] `project_id` (path, string): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### `POST /api/projects/{project_id}/onboarding`

**摘要**: Onboarding

**说明**: 5 步启动链路（v0.4.1 落库）

**operationId**: `onboarding_api_projects__project_id__onboarding_post`

**Parameters**:
- [✓] `project_id` (path, string): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### `POST /api/projects/{project_id}/rollback`

**摘要**: Rollback Project

**说明**: ⚠️ 危险操作：回档 — 薄路由，调 rollback_base tool（v0.4.1 落库）

**operationId**: `rollback_project_api_projects__project_id__rollback_post`

**Parameters**:
- [✓] `project_id` (path, string): 
- [✓] `to_chapter` (query, integer): 
- [✓] `confirm` (query, boolean): Must be true

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## chapters

### `GET /api/projects/{project_id}/chapters`

**摘要**: List Chapters

**说明**: 列章节

**operationId**: `list_chapters_api_projects__project_id__chapters_get`

**Parameters**:
- [✓] `project_id` (path, string): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### `POST /api/projects/{project_id}/chapters`

**摘要**: Generate Chapter

**说明**: 生成下一章（60-100s 端到端）— 薄路由，只调 tool（v0.4.1 落库）

**operationId**: `generate_chapter_api_projects__project_id__chapters_post`

**Parameters**:
- [✓] `project_id` (path, string): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### `GET /api/projects/{project_id}/chapters/{n}`

**摘要**: Read Chapter

**说明**: 读章节正文

**operationId**: `read_chapter_api_projects__project_id__chapters__n__get`

**Parameters**:
- [✓] `project_id` (path, string): 
- [✓] `n` (path, integer): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## projects

### `GET /api/projects`

**摘要**: List Projects

**说明**: 列出项目（默认过滤已删除）

**operationId**: `list_projects_api_projects_get`

**Parameters**:
- [ ] `limit` (query, integer): 
- [ ] `offset` (query, integer): 
- [ ] `include_deleted` (query, boolean): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### `POST /api/projects`

**摘要**: Create Project

**说明**: 创建项目（v0.4.1 落库到 messages 表）

**operationId**: `create_project_api_projects_post`

**Responses**:
- `201`: Successful Response
- `422`: Validation Error

### `GET /api/projects/{project_id}`

**摘要**: Get Project

**说明**: 加载项目详情

**operationId**: `get_project_api_projects__project_id__get`

**Parameters**:
- [✓] `project_id` (path, string): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### `DELETE /api/projects/{project_id}`

**摘要**: Delete Project

**说明**: ⚠️ 危险操作：删除项目（v1.3 软删方案 b）— 薄路由，调 manager.soft_delete

**operationId**: `delete_project_api_projects__project_id__delete`

**Parameters**:
- [✓] `project_id` (path, string): 
- [✓] `confirm` (query, boolean): Must be true

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## system

### `GET /api/health`

**摘要**: Health

**说明**: 健康检查（v0.3 移出到独立文件）

**operationId**: `health_api_health_get`

**Responses**:
- `200`: Successful Response

### `GET /api/info`

**摘要**: Info

**说明**: 版本 + LLM provider 列表

**operationId**: `info_api_info_get`

**Responses**:
- `200`: Successful Response
