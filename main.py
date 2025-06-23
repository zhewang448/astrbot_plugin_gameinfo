import time
import os
import logging
import json
import shutil #用于test
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core.config.astrbot_config import AstrBotConfig
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions # 导入 Edge Options
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager # 导入 Edge DriverManager
from webdriver_manager.firefox import GeckoDriverManager


@register("astrbot_plugin_gameinfo", "bushikq", "一个获取部分二游角色wiki信息的插件", "1.0.5")
class FzInfoPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_gameinfo")
        self.plugin_dir = os.path.dirname(__file__)
        self.assets_dir = os.path.join(self.plugin_dir, "assets")
        # if shutil.os.path.exists(self.assets_dir): #test
        #     shutil.rmtree(self.assets_dir)
        os.makedirs(self.assets_dir, exist_ok=True)
        self.config = config
        self.enable_log_output = self.config.get("enable_log_output", False)
        # 新增浏览器类型配置，默认仍为chrome
        self.browser_type = self.config.get("browser_type", "chrome").lower()

        self.logger = logging.getLogger("astrbot_plugin_gameinfo")
        if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.INFO)
        if self.enable_log_output:
            self.logger.setLevel(logging.INFO) # 日志等级 可以根据需要调整
        else:
            self.logger.setLevel(logging.ERROR)
        self.logger.info("明日方舟wiki插件初始化中...")
        self.gamelist = {"fz":{"url":"https://prts.wiki/w","output_dir":os.path.join(self.assets_dir, "fzassets"),},
                         "ys":{"url":"https://homdgcat.wiki/gi","output_dir":os.path.join(self.assets_dir, "ysassets"),},
                         "sr":{"url":"https://homdgcat.wiki/sr","output_dir":os.path.join(self.assets_dir, "srassets")}}
        self._handle_config_schema() # 调用处理配置文件方法

    def _handle_config_schema(self) -> None:
        """处理配置文件,确保它在正确的位置"""
        schema_content ={
            "enable_log_output": {
                "description": "是否在终端输出详细日志信息",
                "type": "bool",
                "hint": "true/false",
                "default": False
            },
            "browser_type": { 
                "description": "用于网页截图的浏览器类型 (chrome 或 edge)",
                "type": "string",
                "hint": "chrome/edge/firefox", 
                "default": "chrome"
            }
        }
        config_path = self.data_dir / "_conf_schema.json"
        
        # 如果配置文件不存在,创建它
        if not config_path.exists():
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(schema_content, f, ensure_ascii=False, indent=4)
    
    async def game_info_handler(self, event: AstrMessageEvent, game: str = None, character: str = None):
        output_dir = self.gamelist[game]["output_dir"]
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{character}.png")
        if os.path.exists(output_path):
            if time.time() - os.path.getmtime(output_path) < 3600:  # 1小时缓存
                yield event.image_result(output_path)
                return
            else:
                os.remove(output_path)# 缓存过期，删除旧的截图
        url = await self.get_url(game=game, character=character)
        if not url:
            yield event.text_result("游戏名输入错误，请重新输入")
            return
        if not character:
            yield event.text_result("角色名不能为空")
            return
        try:
            await self.take_full_screenshot(url, output_path, 2)
            yield event.image_result(output_path)
        except Exception as e:
            self.logger.error(f"截图失败: {str(e)}")
    @filter.command("srinfo")
    async def sr_handler(self, event: AstrMessageEvent, character: str = None):
        """输入 srinfo [角色名]    返回角色信息截图""" 
        async for ret in self.game_info_handler(event=event, game="sr", character=character):
            yield ret 

    @filter.command("fzinfo")
    async def fz_handler(self, event: AstrMessageEvent, character: str = None):
        """输入 fzinfo [角色名]    返回角色信息截图""" 
        async for ret in self.game_info_handler(event=event, game="fz", character=character):
            yield ret

    @filter.command("ysinfo")
    async def ys_handler(self, event: AstrMessageEvent, character: str = None):
        """输入 ysinfo [角色名]    返回角色信息截图""" 
        async for ret in self.game_info_handler(event=event, game="ys", character=character):
            yield ret

    async def get_url(self, game: str, character: str):
        if game in self.gamelist:
            # if game == "sr":
            #     url = f"{self.gamelist[game]['url']}/{character}/战斗"
            # else:
            url = f"{self.gamelist[game]['url']}/{character}"
            return url
        else:
            return None

    async def take_full_screenshot(self, url: str, output_path: str, delay: int = 10) -> bool:
        """
        截取指定网站的完整页面截图并保存到本地
        
        Args:
            url: 要截图的网站URL
            output_path: 截图保存路径
            delay: 页面加载等待时间(秒)
            
        Returns:
            bool: 截图是否成功
        """
        try:
            self.logger.info(f"开始截图: {url}")
            driver = None
            service = None
            if self.browser_type == "edge": # 添加 Edge 支持
                options = EdgeOptions()
            elif self.browser_type == "firefox": # 添加 Firefox 支持
                options = FirefoxOptions()
            else: # 默认为 Chrome
                options = ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--allow-insecure-localhost')
            options.add_argument('--log-level=3')
            if self.browser_type == "edge":
                service = webdriver.edge.service.Service(EdgeChromiumDriverManager().install())
                driver = webdriver.Edge(service=service, options=options)
            elif self.browser_type == "firefox":
                service = webdriver.firefox.service.Service(GeckoDriverManager().install())
                driver = webdriver.Firefox(service=service, options=options)
            else:
                service = webdriver.chrome.service.Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
            with driver:
                driver.get(url)
                scroll_segments = 5 # 将页面分成 5 段滚动
                initial_height = 0
                scroll_pause_time = .75  # 每段滑动后等待0.75秒，可根据需要调整

                for i in range(scroll_segments):
                    driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight / {scroll_segments} * ({i + 1}));")
                    time.sleep(scroll_pause_time)

                    new_height = driver.execute_script("return document.body.scrollHeight")
                    if new_height > initial_height:
                        self.logger.info(f"滚动到第 {i+1} 段，新高度: {new_height}px")
                        initial_height = new_height 
                    else:
                        self.logger.info(f"滚动到第 {i+1} 段，高度未变化。")
                    if i == scroll_segments - 1:
                         driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                         time.sleep(scroll_pause_time) # 确保最终完全滚动到底部并等待
                # 最终确认页面内容稳定
                # WebDriverWait(driver, delay).until(EC.visibility_of_element_located((By.ID, "mw-content-text")))
                # self.logger.info("页面内容加载完成")

                final_total_height = driver.execute_script("return document.body.scrollHeight")
                self.logger.info(f"页面最终总高度: {final_total_height}px")
                last_height = final_total_height
                last_height = 7000 if "ys" in output_path or "sr" in output_path else last_height # 对于不适配的原神崩铁页面进行强制截取长度（待改良）
                # last_height = driver.execute_script("return document.body.scrollHeight")#测试
                driver.set_window_size(1920, last_height)
                driver.save_screenshot(output_path)
                self.logger.info(f"截图成功保存到: {output_path}")
                return True
                
        except Exception as e:
            self.logger.error(f"截图失败: {str(e)}", exc_info=True)
            return False
        
    @filter.command("getscreenshot")
    async def getscreenshot_handler(self, event: AstrMessageEvent, url: str):
        """输入 getscreenshot [URL] 获取网页截图"""
        output_path = os.path.join(self.assets_dir, "temp_screenshot.png")
        success = await self.take_full_screenshot(url=url, output_path=output_path)
        if success:
            yield event.image_result(output_path)
        else:
            yield event.text_result("截图失败，请检查URL是否正确")