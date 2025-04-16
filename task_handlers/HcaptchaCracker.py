import asyncio
import json
import os
import yaml
from camoufox.async_api import AsyncCamoufox
from hcaptcha_challenger.agent import AgentV, AgentConfig
from hcaptcha_challenger.models import CaptchaResponse, ChallengeSignal
from hcaptcha_challenger.utils import SiteKey
from common.logger import get_logger

logger = get_logger("HCaptcha")

with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)
gemini_key = config.get("apikey").get("gemini_api_key")
# models = config.get("models")
headless_str = config.get("camoufox").get("headless", "true")
headless = headless_str.lower() == "true"
# if gemini_key:
#     os.environ["GEMINI_API_KEY"] = gemini_key
# else:
#     raise RuntimeError("config.yaml 缺少 gemini_api_key")

async def run(task_data, proxy):
    url = task_data["websiteURL"]
    sitekey = task_data["websiteKey"]
    action = task_data.get("metadata", {}).get("action", "")
    cdata = task_data.get("metadata", {}).get("cdata", "")

    logger.info(f"🌐 Preparing hCaptcha page at {url}")

    async with AsyncCamoufox(
        headless=False,
        proxy=proxy,
        geoip=True,
        args=["--lang=en-US", "--accept-language=en-US,en;q=0.9"]
    ) as browser:
        page = await browser.new_page()
        await page.goto(SiteKey.as_site_link(sitekey))

        # 初始化 Agent
        agent_config = AgentConfig(
            GEMINI_API_KEY=gemini_key,
            EXECUTION_TIMEOUT = 300,
            RESPONSE_TIMEOUT = 30,
            RETRY_ON_FAILURE = True,
            # CHALLENGE_CLASSIFIER_MODEL=models['CHALLENGE_CLASSIFIER_MODEL'],
            # IMAGE_CLASSIFIER_MODEL=models['IMAGE_CLASSIFIER_MODEL'],
            # SPATIAL_POINT_REASONER_MODEL=models['SPATIAL_POINT_REASONER_MODEL'],
            # SPATIAL_PATH_REASONER_MODEL=models['SPATIAL_PATH_REASONER_MODEL'],
        )
        agent = AgentV(page=page, agent_config=agent_config)

        await agent.robotic_arm.click_checkbox()

        # 执行挑战并等待结果
        await agent.wait_for_challenge()

        if agent.cr_list:
            cr = agent.cr_list[-1]
            cr_data = cr.model_dump()
            print(cr_data)
            token = cr_data["c"]['req'] if cr_data.get("is_pass") else None
            return {
                "token": token,
                "elapsed": cr_data.get("expiration", 0),
                "status": "success" if cr_data.get("pass") else "failure",
                "type": "hcaptcha"
            }

        # 如果失败了（cr_list 为空）
        return {
            "token": None,
            "elapsed": 0,
            "status": "failure",
            "type": "hcaptcha"
        }

# if __name__ == "__main__":
#     task_data = {
#         "websiteURL": "https://faucet.n1stake.com/",
#         "websiteKey": "d0ba98cc-0528-41a0-98fe-dc66945e5416"
#     }
#     proxy = {
#         "server": "http://pr-sg.ip2world.com:6001",
#         "username": "capsolver-zone-resi-region-hk",
#         "password": "123456"
#     }
#
#     token = asyncio.run(run(task_data, proxy))
#     print(token)