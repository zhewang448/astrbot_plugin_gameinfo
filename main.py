import time
import os
import logging
import json
import shutil
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core.config.astrbot_config import AstrBotConfig
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


@register("astrbot_plugin_gameinfo", "bushikq", "一个获取部分二游角色wiki信息的插件", "1.0.0")
class FzInfoPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_gameinfo")
        self.plugin_dir = os.path.dirname(__file__)
        self.assets_dir = os.path.join(self.plugin_dir, "assets")
        if shutil.os.path.exists(self.assets_dir): #为确保及时性，每次重载插件的时候删除旧的截图
            shutil.rmtree(self.assets_dir)
        self.config = config
        self.enable_log_output = self.config.get("enable_log_output", False)
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

    def _handle_config_schema(self) -> None:
        """处理配置文件,确保它在正确的位置"""
        schema_content ={
            "enable_log_output": {
                "description": "是否在终端输出详细日志信息",
                "type": "bool",
                "hint": "true/false",
                "default": False
            }
        }
        config_path = self.data_dir / "_conf_schema.json"
        
        # 如果配置文件不存在,创建它
        if not config_path.exists():
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(schema_content, f, ensure_ascii=False, indent=4)
    
    async def game_info_handler(self, event: AstrMessageEvent, game: str = None, character: str = None):
        url = await self.get_url(game=game, character=character)
        if not url:
            yield event.text_result("游戏名输入错误，请重新输入")
            return
        if not character:
            yield event.text_result("角色名不能为空")
            return
        try:
            output_dir = self.gamelist[game]["output_dir"]
            os.makedirs(output_dir, exist_ok=True)
            output_path = f"{output_dir}/{character}.png"
            if os.path.exists(output_path):
                yield event.image_result(output_path)
                self.logger.info(f" {character} 信息截图已存在，直接发送图片")
            else:
                await self.take_full_screenshot(url, output_path, 2)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
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

    @filter.command("getscreenshot")
    async def take_full_screenshot(self, url: str, output_path: str = f"{os.path.dirname(__file__)} /test.png", delay: int = 10) -> bool:
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
            # 设置Chrome选项
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--ignore-certificate-errors') # 忽略证书错误
            chrome_options.add_argument('--allow-insecure-localhost') # 允许不安全的本地主机
            chrome_options.add_argument('--log-level=3') # chrome日志等级
            # 初始化浏览器
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                # 访问目标网站
                driver.get(url)
                scroll_segments = 5  # 将页面分成 5 段滚动
                initial_height = 0
                scroll_pause_time = .75 # 每段滑动后等待0.75秒，可根据需要调整

                for i in range(scroll_segments):
                    # 每次向下滚动一个屏幕的高度或计算出的段高
                    # 这里选择滚动到当前可视窗口底部，然后循环直到总高度不再变化
                    driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight / {scroll_segments} * ({i + 1}));")
                    time.sleep(scroll_pause_time) # 每次滚动后短暂等待，让内容有机会加载和渲染

                    # 获取滚动后的
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

                # 获取最终页面总高度
                final_total_height = driver.execute_script("return document.body.scrollHeight")
                self.logger.info(f"页面最终总高度: {final_total_height}px")
                last_height = final_total_height
                last_height = 7000 if "ys" in output_path or "sr" in output_path else last_height # 对于不适配的原神崩铁页面进行强制截取长度（待改良）
                # # 设置浏览器窗口大小
                # last_height = driver.execute_script("return document.body.scrollHeight")#测试
                driver.set_window_size(1920, last_height)
                # 截取完整页面
                driver.save_screenshot(output_path)
                self.logger.info(f"截图成功保存到: {output_path}")
                return True
                
            except Exception as e:
                self.logger.error(f"截图过程中发生错误: {str(e)}")
                return False
                
            finally:
                driver.quit()
                
        except Exception as e:
            self.logger.error(f"浏览器初始化失败: {str(e)}")
            return False