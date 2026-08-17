"""探测 MinIO 对预签名 GET 的 CORS / Range 响应头行为（交接文档 17 批次1 验收辅助）。

确认两件事：
1. 带 Origin 的跨源请求是否返回 Access-Control-Allow-Origin（决定 iframe/PDF.js 能否跨源取）；
2. 带 Range 的请求是否返回 206 + Content-Range + Accept-Ranges（决定 PDF 能否秒开按页取）。

跑完即删（临时探测脚本）。
"""
import urllib.request
import urllib.error
from pathlib import Path

import boto3
from botocore.client import Config
from urllib.parse import quote

env = {}
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

endpoint = env["MINIO_ENDPOINT"]
bucket = env["MINIO_MATERIALS_BUCKET"]
client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=env["MINIO_ACCESS_KEY"],
    aws_secret_access_key=env["MINIO_SECRET_KEY"],
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)

# 拿一个真实 PDF 对象
r = client.list_objects_v2(Bucket=bucket, MaxKeys=10)
pdfs = [o for o in r.get("Contents", []) if o["Key"].lower().endswith(".pdf")]
if not pdfs:
    print("没找到 PDF 对象，拿第一个对象测")
    obj = r["Contents"][0]
else:
    obj = pdfs[0]
key = obj["Key"]
print(f"测试对象: {key} ({obj['Size']} bytes)\n")

# 生成预签名 GET URL（inline，模拟后端 presign_material_get）
url = client.generate_presigned_url(
    "get_object",
    Params={"Bucket": bucket, "Key": key, "ResponseContentDisposition": "inline"},
    ExpiresIn=300,
)


def probe(label, headers):
    req = urllib.request.Request(url, headers=headers)
    print(f"=== {label} ===")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
        hdrs = resp.headers
    except urllib.error.HTTPError as e:
        status = e.code
        hdrs = e.headers
    print(f"  status: {status}")
    interesting = [
        "Access-Control-Allow-Origin",
        "Access-Control-Allow-Methods",
        "Access-Control-Expose-Headers",
        "Access-Control-Allow-Credentials",
        "Content-Length",
        "Content-Range",
        "Accept-Ranges",
        "ETag",
        "Content-Disposition",
        "Cache-Control",
        "Vary",
    ]
    for k in interesting:
        v = hdrs.get(k)
        if v is not None:
            print(f"  {k}: {v}")
    print()


# 1) 带 Origin 的 GET（看 CORS 头）
probe("GET + Origin: localhost:5173 (无 Range)", {"Origin": "http://localhost:5173"})

# 2) 带 Origin + Range（看 CORS + 206）
probe(
    "GET + Origin + Range: bytes=0-1023",
    {"Origin": "http://localhost:5173", "Range": "bytes=0-1023"},
)

# 3) OPTIONS 预检（PDF.js 会发）
req = urllib.request.Request(url, method="OPTIONS", headers={
    "Origin": "http://localhost:5173",
    "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Headers": "range",
})
print("=== OPTIONS 预检 ===")
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"  status: {resp.status}")
    for k in ["Access-Control-Allow-Origin", "Access-Control-Allow-Methods",
              "Access-Control-Allow-Headers", "Access-Control-Max-Age"]:
        v = resp.headers.get(k)
        if v is not None:
            print(f"  {k}: {v}")
except urllib.error.HTTPError as e:
    print(f"  status: {e.code}")
    for k in ["Access-Control-Allow-Origin", "Access-Control-Allow-Methods",
              "Access-Control-Allow-Headers"]:
        v = e.headers.get(k)
        if v is not None:
            print(f"  {k}: {v}")
    print(f"  (MinIO 可能对预签名 URL 的 OPTIONS 不做预检处理，这在 iframe 模式下不影响)")
