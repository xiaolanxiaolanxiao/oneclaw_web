import json, random, string, time, base64
from alibabacloud_eci20180808.client import Client as EciClient
from alibabacloud_eci20180808 import models as eci_models
from alibabacloud_alidns20150109.client import Client as DnsClient
from alibabacloud_alidns20150109 import models as dns_models
from alibabacloud_tea_openapi import models as open_api_models

REGION = 'cn-hangzhou'
MAIN_DOMAIN = 'aichatgpt.plus' # 你的已备案主域名

# 🌟 OpenClaw 配置常量
OPENAI_BASE_URL = 'https://chatapi.kindsoft.vip/v1'
OPENAI_API_KEY = 'sk-ffPd1kc8jdjxpp1SQN4yTA2g5dy5YQ02JXuIW5XtFVd0952v'

def handler(event, context):
    creds = context.credentials
    
    # ✅ 修复：恢复极简的统一配置，必须包含 region_id，让 SDK 自动解析和签名
    config = open_api_models.Config(
        access_key_id=creds.access_key_id, 
        access_key_secret=creds.access_key_secret,
        security_token=creds.security_token, 
        region_id=REGION
    )
    
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    GATEWAY_TOKEN = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    instance_name = f"openclaw-{int(time.time())}"

    # ====================================================
    # 0. 使用 EmptyDir + Init Container 注入配置文件
    # ====================================================
    # ConfigFileVolume 是只读的，但 OpenClaw 需要在 ~/.openclaw/ 下创建子目录
    # 所以改用 EmptyDir（可读写）+ Init Container 预写配置文件
    
    env_content = f"OPENCLAW_GATEWAY_TOKEN={GATEWAY_TOKEN}\\nOPENAI_BASE_URL={OPENAI_BASE_URL}\\nOPENAI_API_KEY={OPENAI_API_KEY}\\n"
    
    openclaw_config = json.dumps({
        "gateway": {
            "mode": "local",
            "controlUi": {
                "dangerouslyAllowHostHeaderOriginFallback": True,
                "allowInsecureAuth": True,
                "dangerouslyDisableDeviceAuth": True
            },
            "auth": {
                "mode": "token",
                "token": GATEWAY_TOKEN
            }
        },
        "agents": {
            "defaults": {
                "maxConcurrent": 4,
                "model": {
                    "primary": "custom/doubao-seed-code"
                },
                "subagents": {
                    "maxConcurrent": 8
                }
            }
        },
        "models": {
            "mode": "merge",
            "providers": {
                "custom": {
                    "baseUrl": OPENAI_BASE_URL,
                    "apiKey": OPENAI_API_KEY,
                    "api": "openai-completions",
                    "models": [
                        {
                            "id": "doubao-seed-code",
                            "name": "doubao-seed-code",
                            "api": "openai-completions",
                            "reasoning": False,
                            "input": ["text", "image"],
                            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                            "contextWindow": 200000,
                            "maxTokens": 8192
                        }
                    ]
                }
            }
        },
    })
    
    # 初始化脚本：写入配置文件 + 创建所需子目录
    init_script = f"""echo '{env_content}' > /openclaw-config/.env
echo '{openclaw_config}' > /openclaw-config/openclaw.json
mkdir -p /openclaw-config/canvas /openclaw-config/cron /openclaw-config/workspace
chown -R 1000:1000 /openclaw-config
"""
    
    # EmptyDir 卷（可读写，init container 和 openclaw 容器共享）
    config_volume = eci_models.CreateContainerGroupRequestVolume(
        name='openclaw-config',
        type='EmptyDirVolume',
        empty_dir_volume=eci_models.CreateContainerGroupRequestVolumeEmptyDirVolume()
    )
    
    # Init Container: 用 busybox 写入配置文件
    init_container = eci_models.CreateContainerGroupRequestInitContainer(
        name='config-init',
        image='docker.1ms.run/library/nginx:alpine',
        command=["/bin/sh", "-c"],
        arg=[init_script],
        volume_mount=[
            eci_models.CreateContainerGroupRequestInitContainerVolumeMount(
                name='openclaw-config',
                mount_path='/openclaw-config'
            )
        ]
    )

    # ====================================================
    # 1. OpenClaw Web 容器 (包含 Web UI + Gateway + Nginx)
    # ====================================================
    container_openclaw = eci_models.CreateContainerGroupRequestContainer(
        name="openclaw-web", 
        image='crpi-71isp0aellmb4yns.cn-hangzhou.personal.cr.aliyuncs.com/oneclaw0312/oneclaw-web:v1',
        cpu=0.75, memory=1.5,
        # 🌟 同时通过环境变量注入
        environment_var=[
            eci_models.CreateContainerGroupRequestContainerEnvironmentVar(key='HOME', value='/home/node'),
            eci_models.CreateContainerGroupRequestContainerEnvironmentVar(key='TERM', value='xterm-256color'),
            eci_models.CreateContainerGroupRequestContainerEnvironmentVar(key='OPENCLAW_GATEWAY_TOKEN', value=GATEWAY_TOKEN),
            eci_models.CreateContainerGroupRequestContainerEnvironmentVar(key='OPENAI_BASE_URL', value=OPENAI_BASE_URL),
            eci_models.CreateContainerGroupRequestContainerEnvironmentVar(key='OPENAI_API_KEY', value=OPENAI_API_KEY),
        ],
        # 💥 移除 command 和 arg 覆盖，使用镜像内自带的 CMD ["/app/entrypoint.sh"] 来同时启动前、后端
        # 🌟 挂载 EmptyDir 到 ~/.openclaw/ 目录（可读写）
        volume_mount=[
            eci_models.CreateContainerGroupRequestContainerVolumeMount(
                name='openclaw-config',
                mount_path='/home/node/.openclaw/',
                read_only=False
            )
        ]
    )
    
    # 2. Nginx HTTPS 反向代理（无需认证，直接透传）
    startup_script = """# 🌟 写入证书公钥
cat << 'EOF' > /etc/nginx/cert.pem
-----BEGIN CERTIFICATE-----
MIIFEzCCA/ugAwIBAgISBjQVWnG3NNcD6VvIHPbsR1G9MA0GCSqGSIb3DQEBCwUA
MDMxCzAJBgNVBAYTAlVTMRYwFAYDVQQKEw1MZXQncyBFbmNyeXB0MQwwCgYDVQQD
EwNSMTIwHhcNMjYwMTEzMTc0MjE0WhcNMjYwNDEzMTc0MjEzWjAbMRkwFwYDVQQD
DBAqLmFpY2hhdGdwdC5wbHVzMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKC
AQEAxQ7/jH42rj2pwEagGs9TDG2Y6IP6vXvEtECOIkRQVt8NhtRynbfuWnFuZghH
o7H+uOeXUW2Db+QDtr4ZbMrh2fW6mkPWCdwp+ngM7KD3aDQnouUvHoEIK1rz4uva
KmJW400QjLWsWUv8To0l8j5osl3k2Cb4z427dre0EfziIL8t1kfhRkK9VMmUJbRV
PW4lDK0FgIjTWNSFAQQCeHFaQGTHwSoPtoEDY280HBt0Dg1xDq2sAdbvucmFN+T7
87/Lndd4VScXKvrYXYx54Xg+IffgrcLooQVWdEpjHS9mRDF0Z33C0W6R3VygCZH6
Kdqc/5+WH1Bp12AS74AoO6dOFwIDAQABo4ICNzCCAjMwDgYDVR0PAQH/BAQDAgWg
MB0GA1UdJQQWMBQGCCsGAQUFBwMBBggrBgEFBQcDAjAMBgNVHRMBAf8EAjAAMB0G
A1UdDgQWBBTd4qQtzmZ2+wUa0Yr6y4iwtzuWzDAfBgNVHSMEGDAWgBQAtSnyLY5v
MeibTK14Pvrc6QzR0jAzBggrBgEFBQcBAQQnMCUwIwYIKwYBBQUHMAKGF2h0dHA6
Ly9yMTIuaS5sZW5jci5vcmcvMCsGA1UdEQQkMCKCECouYWljaGF0Z3B0LnBsdXOC
DmFpY2hhdGdwdC5wbHVzMBMGA1UdIAQMMAowCAYGZ4EMAQIBMC4GA1UdHwQnMCUw
I6AhoB+GHWh0dHA6Ly9yMTIuYy5sZW5jci5vcmcvNjIuY3JsMIIBCwYKKwYBBAHW
eQIEAgSB/ASB+QD3AHUAyzj3FYl8hKFEX1vB3fvJbvKaWc1HCmkFhbDLFMMUWOcA
AAGbuKkJ2QAABAMARjBEAiBsPe/qGL+zVGvq4yObUc3eHSpB5mIUSneUebKwv3wT
DAIgChL5qbgGOQGygeR0VD0588FQboFvYGsXdlAL6WGBLakAfgAai51pSleYyJmg
yoi99I/AtFZgzMNgDR9x9Gn/x9GsowAAAZu4qQurAAgAAAUANmzUrAQDAEcwRQIg
DIRrOzLlwrFVoVdg4WUvi08Ig+uNCon8OEbTMdtj7eoCIQCFoqnNLOboU7Bru5RT
0T4EKRPy8vT0OuoK0fQAKKJbNjANBgkqhkiG9w0BAQsFAAOCAQEAVLsNDNnM0a3e
N+rnpCa5TZF3fQHBeSwCQ/SX/+TpdqeYK2p0m6BnhqHM6tE9a3hUsxkUAVUiJBp9
2iTILfAh6Nl7ATccyNSI1BV3fku1DY0pHVwE6c5selknJ5mPTq6qDNuJayzqyIe1
W8Tk9zLp327gw+f5nCsd0xralftMB4Chz8T9Z9EYjuPHDR2cUuOiTOTZLHNgCppQ
7oRCKZpDGlkoccrJahld+d7hdtxsYGRzMX9wQIKQ+S9rkHKq1zF2kBBCMSgNNvXK
lxlVcFBH3r1ACbW6InHoiygjfSYkWd2zCV5VAua8udLOG4gwSfcbP0BuMSblFBri
FYnE/w2xSQ==
-----END CERTIFICATE-----

-----BEGIN CERTIFICATE-----
MIIFBjCCAu6gAwIBAgIRAMISMktwqbSRcdxA9+KFJjwwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMjQwMzEzMDAwMDAw
WhcNMjcwMzEyMjM1OTU5WjAzMQswCQYDVQQGEwJVUzEWMBQGA1UEChMNTGV0J3Mg
RW5jcnlwdDEMMAoGA1UEAxMDUjEyMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB
CgKCAQEA2pgodK2+lP474B7i5Ut1qywSf+2nAzJ+Npfs6DGPpRONC5kuHs0BUT1M
5ShuCVUxqqUiXXL0LQfCTUA83wEjuXg39RplMjTmhnGdBO+ECFu9AhqZ66YBAJpz
kG2Pogeg0JfT2kVhgTU9FPnEwF9q3AuWGrCf4yrqvSrWmMebcas7dA8827JgvlpL
Thjp2ypzXIlhZZ7+7Tymy05v5J75AEaz/xlNKmOzjmbGGIVwx1Blbzt05UiDDwhY
XS0jnV6j/ujbAKHS9OMZTfLuevYnnuXNnC2i8n+cF63vEzc50bTILEHWhsDp7CH4
WRt/uTp8n1wBnWIEwii9Cq08yhDsGwIDAQABo4H4MIH1MA4GA1UdDwEB/wQEAwIB
hjAdBgNVHSUEFjAUBggrBgEFBQcDAgYIKwYBBQUHAwEwEgYDVR0TAQH/BAgwBgEB
/wIBADAdBgNVHQ4EFgQUALUp8i2ObzHom0yteD763OkM0dIwHwYDVR0jBBgwFoAU
ebRZ5nu25eQBc4AIiMgaWPbpm24wMgYIKwYBBQUHAQEEJjAkMCIGCCsGAQUFBzAC
hhZodHRwOi8veDEuaS5sZW5jci5vcmcvMBMGA1UdIAQMMAowCAYGZ4EMAQIBMCcG
A1UdHwQgMB4wHKAaoBiGFmh0dHA6Ly94MS5jLmxlbmNyLm9yZy8wDQYJKoZIhvcN
AQELBQADggIBAI910AnPanZIZTKS3rVEyIV29BWEjAK/duuz8eL5boSoVpHhkkv3
4eoAeEiPdZLj5EZ7G2ArIK+gzhTlRQ1q4FKGpPPaFBSpqV/xbUb5UlAXQOnkHn3m
FVj+qYv87/WeY+Bm4sN3Ox8BhyaU7UAQ3LeZ7N1X01xxQe4wIAAE3JVLUCiHmZL+
qoCUtgYIFPgcg350QMUIWgxPXNGEncT921ne7nluI02V8pLUmClqXOsCwULw+PVO
ZCB7qOMxxMBoCUeL2Ll4oMpOSr5pJCpLN3tRA2s6P1KLs9TSrVhOk+7LX28NMUlI
usQ/nxLJID0RhAeFtPjyOCOscQBA53+NRjSCak7P4A5jX7ppmkcJECL+S0i3kXVU
y5Me5BbrU8973jZNv/ax6+ZK6TM8jWmimL6of6OrX7ZU6E2WqazzsFrLG3o2kySb
zlhSgJ81Cl4tv3SbYiYXnJExKQvzf83DYotox3f0fwv7xln1A2ZLplCb0O+l/AK0
YE0DS2FPxSAHi0iwMfW2nNHJrXcY3LLHD77gRgje4Eveubi2xxa+Nmk/hmhLdIET
iVDFanoCrMVIpQ59XWHkzdFmoHXHBV7oibVjGSO7ULSQ7MJ1Nz51phuDJSgAIU7A
0zrLnOrAj/dfrlEWRhCvAgbuwLZX1A2sjNjXoPOHbsPiy+lO1KF8/XY7
-----END CERTIFICATE-----
EOF

# 🌟 写入证书私钥
cat << 'EOF' > /etc/nginx/cert.key
-----BEGIN RSA PRIVATE KEY-----
MIIEpQIBAAKCAQEAxQ7/jH42rj2pwEagGs9TDG2Y6IP6vXvEtECOIkRQVt8NhtRy
nbfuWnFuZghHo7H+uOeXUW2Db+QDtr4ZbMrh2fW6mkPWCdwp+ngM7KD3aDQnouUv
HoEIK1rz4uvaKmJW400QjLWsWUv8To0l8j5osl3k2Cb4z427dre0EfziIL8t1kfh
RkK9VMmUJbRVPW4lDK0FgIjTWNSFAQQCeHFaQGTHwSoPtoEDY280HBt0Dg1xDq2s
AdbvucmFN+T787/Lndd4VScXKvrYXYx54Xg+IffgrcLooQVWdEpjHS9mRDF0Z33C
0W6R3VygCZH6Kdqc/5+WH1Bp12AS74AoO6dOFwIDAQABAoIBAAN3hRVyrwGXwiHI
3E48cYiZcQQ+Ni4ZPFezfwypSQSOPg2uNSoDL2VV84xF/wSpQAL+yBG9rH9OcqZH
Z+kbFKgiA5ttMBnSTsbCT+/l0RR7PmtGPvL5cCxbGElYvujZ/A9Zrr3bAGI9zP2Q
zCcb4/mnXzxSSzRTmQW4q6lZWp0a2AtbGZCXAglGjpe4PcVwLaeVh82RPolG682J
yBSsll37OLn1DVrr4ZlWvp17CKZI99DmaEDyg2XB84eGDFBgGuNxpyoVRTDLaTpt
/FGl8fhVs6fU2uJytY64+Av4VH2hl00QelNH7hU6L1dT+hOJxd8bYbIrEs90G5lu
9I5ACeECgYEA4kG+3zjoR8X9JEHcBIA+PPDe5MNSAeOP40Hu0rnuBrCDjgj9qBQ0
qkO9XgrWBLLZ1W1a9LPrECKCOCUlqDm9aktrLjJ/xWRuT0Pf46gQJQZNVjNXGOPp
UB5t3GxepVVUwurAj9+n6GzTa7OL+PPzl6ycx7GWNzH/aL/gSyKwwOcCgYEA3vaj
5CWmQRiME+iLYlm6p4z/xsuis5cjFm6UDMjMzxsvACyQ6jF0a4DeB8CHyvvQVpu5
CZk9uckoYA/0bZwqEJp2Xi026WhGXoGJVwbygdgFIY/YOZRYozbh5/QBuEhSYkyb
lgXsjFGdSG1EFU0G5u7RyBb3CeXIyO2O/emJ81ECgYEA4J3whd8TCp4N737KlFVU
dF+UiHs34NQvtqdwFxeqrE10bP+UAtb8acQSLViIm+WKyI1l7OTpCf2YVXDbb6TS
3MG+yAAuRKKtuFdj37irPnaBNICHiRhKOdXbryaO14hdO5yeSrb5FI9lXNjErwRQ
4lTk2IL+5BDoxO8oFq971iUCgYEAstkxGh9BP1JLeuS8egXz/dbSjUpnlpuTn7jP
tXmVIERz7TXSgKlu85UJhTphMufPdMmxIgv0QYUkh/oEXbA45dyhOmYWeCAW4lQS
MOb3vEPlycgy7+0ZNMMfbwqCHqqUuxksbKkP2HbXLXPIezWwZaoISPJy81OJPfOh
Efg1miECgYEAxLRm4e4w9b96hxq74Lr+goyAGfJCWQ/58hj4A88h5eabh4wVUUbL
bnZNzx+GRplkJrEabIdKHsUIG2n6/hB0YzMAog4OlYqHgLQ+iQlTZ4+z0jnJtw68
HB+swwmVc6pi93RFCubNFr4nbJIpfDmBwsdCcbQ3UMcQeXXi+Z2lJCw=
-----END RSA PRIVATE KEY-----
EOF

# 🌟 Nginx 配置：HTTPS 反向代理给内部 Web 和 Gateway
cat << 'EOF' > /etc/nginx/conf.d/default.conf
server {
    # 💥 这里不可以监听 80，因为同 Pod 的 openclaw-web 的 Nginx 在监听 80 端口！
    listen 443 ssl;
    
    ssl_certificate /etc/nginx/cert.pem;
    ssl_certificate_key /etc/nginx/cert.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    location / {
        # 将流量转发给内部的 oneclaw-web 提供访问（端口 80）
        proxy_pass http://127.0.0.1:80; 
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
nginx -g 'daemon off;'
"""

    container_nginx = eci_models.CreateContainerGroupRequestContainer(
        name="nginx-proxy", 
        image='docker.1ms.run/library/nginx:alpine',
        cpu=0.25, memory=0.5,
        command=["/bin/sh", "-c"], arg=[startup_script]
    )

    # 3. 创建 ECI 实例组
    request = eci_models.CreateContainerGroupRequest(
        region_id=REGION, 
        security_group_id='sg-bp148kzmnq5fnbw5edyu', 
        v_switch_id='vsw-bp1vunnz44ukgeo094u7j',       
        container_group_name=instance_name, 
        container=[container_openclaw, container_nginx],
        # 🌟 Init Container 用于预写配置文件
        init_container=[init_container],
        # 🌟 注册 EmptyDir 卷（可读写，init container 和 openclaw 共享）
        volume=[config_volume],
        cpu=1.0,
        memory=2.0,
        auto_create_eip=True, 
        eip_bandwidth=5,
        auto_match_image_cache=True
    )
    
    # ✅ 统一使用这个 config 初始化 ECI 客户端
    eci_client = EciClient(config) 
    group_id = eci_client.create_container_group(request).body.container_group_id

    # 4. 轮询获取 IP
    public_ip = None
    for _ in range(20):
        time.sleep(2)
        desc = eci_client.describe_container_groups(eci_models.DescribeContainerGroupsRequest(
            region_id=REGION, 
            container_group_ids=f'["{group_id}"]'
        ))
        if desc.body.container_groups[0].internet_ip:
            public_ip = desc.body.container_groups[0].internet_ip
            break

    # 5. 动态添加 DNS 解析记录
    sub_domain_prefix = f"{password[:6].lower()}"
    
    # ✅ 统一使用这个 config 初始化 DNS 客户端
    dns_client = DnsClient(config) 
    dns_client.add_domain_record(dns_models.AddDomainRecordRequest(
        domain_name=MAIN_DOMAIN, rr=sub_domain_prefix, type="A", value=public_ip
    ))

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({
            "url": f"https://{sub_domain_prefix}.{MAIN_DOMAIN}?token={GATEWAY_TOKEN}"
        })
    }