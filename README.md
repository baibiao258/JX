# 打卡脚本 Docker 镜像

自动打卡和日报提交的 Docker 镜像项目。

## 自动构建 (GitHub Actions)

推送代码到 main 分支后，GitHub Actions 会自动构建并推送镜像到 GitHub Container Registry。

无需额外配置，使用 GitHub 自带的 GITHUB_TOKEN 即可。

## 在 Leaflow 上部署

镜像格式: `ghcr.io/baibiao258/jx:v1`

### 环境变量配置

在 Leaflow 创建应用时，需要配置以下环境变量：

| 变量名 | 必填 | 说明 |
|--------|------|------|
| CHECKIN_USERNAME | ✅ | 登录用户名 |
| CHECKIN_PASSWORD | ✅ | 登录密码 |
| WXPUSHER_APP_TOKEN | ❌ | WxPusher 通知 Token |
| WXPUSHER_UID | ❌ | WxPusher 用户 UID |

可选重试配置（失败自动重试）:

| 变量名 | 默认 | 说明 |
|--------|------|------|
| CHECKIN_RETRY_ATTEMPTS | 3 | 打卡最多尝试次数 |
| CHECKIN_RETRY_DELAY | 90 | 打卡重试间隔（秒），后续按回退系数递增 |
| CHECKIN_RETRY_BACKOFF | 1.5 | 打卡重试间隔回退系数 |
| DAILY_REPORT_RETRY_ATTEMPTS | 3 | 日报最多尝试次数 |
| DAILY_REPORT_RETRY_DELAY | 90 | 日报重试间隔（秒），后续按回退系数递增 |
| DAILY_REPORT_RETRY_BACKOFF | 1.5 | 日报重试间隔回退系数 |

### 启动命令

- 打卡: `python auto_checkin.py`
- 日报: `python auto_daily_report.py`

### 资源建议

- 内存: 512 MiB
- CPU: 500 毫核

## 本地测试

```bash
docker run -e CHECKIN_USERNAME=你的用户名 -e CHECKIN_PASSWORD=你的密码 ghcr.io/baibiao258/jx:v1
```
