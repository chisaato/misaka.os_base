# Changelog

## Unreleased

- 变量改名以适配 var-naming[no-role-prefix]（前缀 `tools_`）：`uv_tools` → `tools_list`、`uv_tools_state` → `tools_state`、`uv_tools_bin` → `tools_bin`、`uv_tools_executable` → `tools_executable`、`uv_tools_retries` → `tools_retries`、`uv_tools_retry_delay` → `tools_retry_delay`、`uv_tools_extra_paths` → `tools_extra_paths`

## 0.1.0

- 新增 `misaka.uv.tools`：按 `tools_list` 清单调用 `uv tool install`
