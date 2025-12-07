# 打卡脚本 Docker 镜像

自动打卡和日报提交的 Docker 镜像项目。

## 构建镜像

```bash
docker build -t yourusername/daka4s:v1 .
```

## 推送到 Docker Hub

```bash
docker login
docker push yourusername/daka4s:v1
```

## 在 Leaflow 上部署

镜像格式: `yourusername/daka4s:v1`

### 环境变量配置

在 Leaflow 创建应用时，需要配置以下环境变量：

| 变量名 | 必填 | 说明 |
|--------|------|------|
| CHECKIN_USERNAME | ✅ | 登录用户名 |
| CHECKIN_PASSWORD | ✅ | 登录密码 |
| WXPUSHER_APP_TOKEN | ❌ | WxPusher 通知 Token |
| WXPUSHER_UID | ❌ | WxPusher 用户 UID |

### 启动命令

- 打卡: `python auto_checkin.py`
- 日报: `python auto_daily_report.py`

### 资源建议

- 内存: 512 MiB
- CPU: 500 毫核

## 本地测试

```bash
docker run -e CHECKIN_USERNAME=你的用户名 -e CHECKIN_PASSWORD=你的密码 yourusername/daka4s:v1
```
