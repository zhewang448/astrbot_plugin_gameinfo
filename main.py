import time
import os
import asyncio
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.utils.session_waiter import session_waiter, SessionController
import astrbot.api.message_components as Comp
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.api import logger
from selenium import webdriver
from selenium.webdriver.chrome.options import (
    Options as ChromeOptions,
)  # 导入 ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.microsoft import (
    EdgeChromiumDriverManager,
)  # 导入 Edge DriverManager
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


@register(
    "astrbot_plugin_gameinfo", "bushikq", "一个获取部分二游角色wiki信息的插件", "1.1.8"
)
class FzInfoPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_gameinfo")
        self.plugin_dir = os.path.dirname(__file__)
        self.assets_dir = os.path.join(self.plugin_dir, "assets")
        os.makedirs(self.assets_dir, exist_ok=True)
        self.config = config
        self.browser_type = self.config.get("browser_type", "chrome").lower()
        self.driver_path = (
            self.config.get("driver_path", "").replace("\\", "/").replace('"', "")
        )
        self.keep_temp_time = (
            self.config.get("keep_temp_time", 3600)
        ) * 60  # 截图缓存时间 单位转化为秒
        logger.info("二游wiki插件初始化中...")  # 使用框架自带logger
        self.gamelist = {
            "fz": {
                "url": "https://prts.wiki/w",
                "output_dir": os.path.join(self.assets_dir, "fzassets"),
            },
            "ys": {
                "url": "https://homdgcat.wiki/gi",
                "output_dir": os.path.join(self.assets_dir, "ysassets"),
            },
            "sr": {
                "url": "https://homdgcat.wiki/sr",
                "output_dir": os.path.join(self.assets_dir, "srassets"),
            },
            "zzz": {
                "url": "https://zzz3.hakush.in/character",
                "output_dir": os.path.join(self.assets_dir, "zzzassets"),
            },
            "ww": {
                "url": "https://ww2.hakush.in/character",
                "output_dir": os.path.join(self.assets_dir, "wwassets"),
            },
            "issac": {
                "url": "https://isaac.huijiwiki.com/wiki",
                "output_dir": os.path.join(self.assets_dir, "issacassets"),
            },
        }
        self._handle_config_schema()  # 调用处理配置文件方法
        self._handle_driver_manager()  # 调用浏览器驱动管理方法

    def _handle_config_schema(self) -> None:
        """处理配置文件,确保它在正确的位置"""
        config_path = self.data_dir / "_conf_schema.json"
        if not config_path.exists():
            logger.error("配置文件不存在,请重新下载插件...")

    def _handle_driver_manager(self) -> None:
        self.driver = None
        service = None
        if self.browser_type not in ["chrome", "edge", "firefox"]:
            logger.error(f"不支持的浏览器类型: {self.browser_type}")
            self.browser_type = "chrome"
        if self.driver_path and not os.path.exists(self.driver_path):
            logger.error(f"驱动路径不存在: {self.driver_path}")
            self.driver_path = ""

        def add_argument(options):
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--ignore-certificate-errors")
            options.add_argument("--allow-insecure-localhost")
            options.add_argument("log-level=3")
            options.add_argument("disable-infobars")
            options.add_argument("--disable-logging")
            options.add_experimental_option("excludeSwitches", ["enable-logging"])

        try:
            if self.browser_type == "edge":  # 添加 Edge 支持
                options = EdgeOptions()
                options.add_argument(
                    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59"
                )
                add_argument(options)
                service = (
                    webdriver.edge.service.Service(
                        EdgeChromiumDriverManager().install()
                    )
                    if not self.driver_path
                    else webdriver.edge.service.Service(self.driver_path)
                )
                self.driver = webdriver.Edge(service=service, options=options)
            elif self.browser_type == "firefox":  # 添加 Firefox 支持
                options = FirefoxOptions()
                options.add_argument(
                    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
                )
                add_argument(options)
                service = (
                    webdriver.firefox.service.Service(GeckoDriverManager().install())
                    if not self.driver_path
                    else webdriver.firefox.service.Service(self.driver_path)
                )
                self.driver = webdriver.Firefox(service=service, options=options)
            else:  # 默认为 Chrome
                options = ChromeOptions()
                options.add_argument(
                    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                )
                add_argument(options)
                service = (
                    webdriver.chrome.service.Service(ChromeDriverManager().install())
                    if not self.driver_path
                    else webdriver.chrome.service.Service(self.driver_path)
                )
                self.driver = webdriver.Chrome(service=service, options=options)
            logger.info(f"浏览器驱动初始化成功: {self.browser_type}")
        except Exception as e:
            logger.error(f"浏览器驱动初始化失败: {str(e)},请手动在配置中添加driver地址")

    async def game_info_handler(
        self, event: AstrMessageEvent, game: str = None, character: str = None
    ):
        if not character:
            yield event.plain_result("角色名不能为空")
            return
        if game not in self.gamelist:
            yield event.plain_result("未知游戏")
        yield event.plain_result(f"正在查询{game}中的{character}信息，请稍后...")
        output_dir = self.gamelist[game]["output_dir"]
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{character}.png")
        if os.path.exists(output_path):
            if (
                time.time() - os.path.getmtime(output_path) < self.keep_temp_time
            ):  # 1小时缓存
                yield event.image_result(output_path)
                return
            else:
                os.remove(output_path)  # 缓存过期，删除旧的截图
        url = await self.get_url(game=game, character=character, event=event)
        if url == "no_need_to_return_url":  # 无需返回url，停止
            return
        if not url:
            yield event.plain_result("url获取失败")
            return
        try:
            await self.take_full_screenshot(url, output_path, game, 3)
            yield event.image_result(output_path)
        except Exception as e:
            logger.error(f"截图失败: {str(e)}")

    @filter.command("srinfo", alias={"崩铁wiki查询", "星穹铁道wiki查询"})
    async def sr_handler(self, event: AstrMessageEvent, character: str = None):
        """输入 srinfo [角色名]    返回角色信息截图"""
        async for ret in self.game_info_handler(
            event=event, game="sr", character=character
        ):
            yield ret

    @filter.command("fzinfo", alias={"方舟wiki查询", "明日方舟wiki查询"})
    async def fz_handler(self, event: AstrMessageEvent, character: str = None):
        """输入 fzinfo [角色名]    返回角色信息截图"""
        async for ret in self.game_info_handler(
            event=event, game="fz", character=character
        ):
            yield ret

    @filter.command("ysinfo", alias={"原神wiki查询"})
    async def ys_handler(self, event: AstrMessageEvent, character: str = None):
        """输入 ysinfo [角色名]    返回角色信息截图"""
        async for ret in self.game_info_handler(
            event=event, game="ys", character=character
        ):
            yield ret

    @filter.command("zzzinfo", alias={"绝区零wiki查询"})
    async def zzz_handler(self, event: AstrMessageEvent, character: str = None):
        """输入 zzzinfo [角色名]    返回角色信息截图"""
        async for ret in self.game_info_handler(
            event=event, game="zzz", character=character
        ):
            yield ret

    @filter.command("wwinfo", alias={"鸣潮wiki查询"})
    async def ww_handler(self, event: AstrMessageEvent, character: str = None):
        """输入 wwinfo [角色名]    返回角色信息截图"""
        async for ret in self.game_info_handler(
            event=event, game="ww", character=character
        ):
            yield ret

    @filter.command("issacinfo", alias={"以撒wiki查询"})
    async def issac_handler(self, event: AstrMessageEvent, character: str = None):
        """输入 issacinfo [角色名]    返回角色信息截图"""
        async for ret in self.game_info_handler(
            event=event, game="issac", character=character
        ):
            yield ret

    async def get_url(self, game: str, character: str, event: AstrMessageEvent):
        if game in self.gamelist:
            if game == "zzz" or game == "ww":
                try:
                    logger.info(f"开始尝试获取url: {character}")
                    driver = self.driver
                    driver.get(self.gamelist[game]["url"])
                    character_link_xpath = f"//a[contains(@href, '/character/') and .//div[contains(text(), '{character.split('/')[0]}')]]"
                    # 等待角色链接加载并可点击
                    character_link = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, character_link_xpath))
                    )
                    # 点击角色链接
                    url = character_link.get_attribute("href")
                    logger.info(f"获取到url: {url}")
                    return url
                except Exception as e:
                    logger.error(f"获取url失败: {str(e)}")
                    return False
            elif game == "issac":
                base_url = self.gamelist[game]["url"]
                driver = self.driver
                query_url = f"{base_url}/{character}"
                driver.get(query_url)
                if "这是一个消歧义页" in driver.page_source:  # 检查是否是消歧义页面
                    logger.info(f"检测到以撒消歧义页面: {query_url}")
                    await self._handle_disambiguation_page(
                        original_query=character, query_url=query_url, event=event
                    )
                    return "no_need_to_return_url"
                else:
                    return query_url
            else:
                url = f"{self.gamelist[game]['url']}/{character}"
            return url
        else:
            return None

    async def _handle_disambiguation_page(
        self,
        event: AstrMessageEvent,
        query_url: str,
        original_query: str,
    ):
        """
        处理以撒wiki的消歧义页面，识别所有选项并根据用户消息进行选择和跳转。
        """
        try:
            disambiguation_links = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located(
                    (
                        By.XPATH,
                        "//div[@class='mw-parser-output']/ul/li/span[@class='item']/a | //div[@class='mw-parser-output']/ul/li/span[@style='display:inline-block;']/a",
                    )
                )
            )
            options = []
            for link_element in disambiguation_links:
                title = link_element.get_attribute("title")
                href = link_element.get_attribute("href")
                if title and href:
                    options.append({"title": title, "url": href})

            if not options:
                logger.warning("未能在消歧义页面找到有效选项。")
                event.send(
                    event.plain_result("未能在消歧义页面找到有效选项。杂鱼程序员")
                )
                return None

            logger.info(f"{options}")
            output_path = os.path.join(
                self.gamelist["issac"]["output_dir"],
                f"{original_query}消歧义页.png",
            )
            if (
                not os.path.exists(output_path)
                or time.time() - os.path.getmtime(output_path) > self.keep_temp_time
            ):  # 1小时缓存
                await self.take_full_screenshot(query_url, output_path, "issac")

            msg_components = [
                (Comp.Plain(text="请输入你要查看的选项序号数字\n")),
                Comp.Image.fromFileSystem(output_path),
            ]
            await event.send(event.chain_result(msg_components))

            @session_waiter(timeout=60, record_history_chains=False)
            async def empty_mention_waiter(
                controller: SessionController, event: AstrMessageEvent
            ):
                try:
                    choice = event.message_str
                    if choice == "取消":
                        logger.info("用户取消选择")
                        await event.send(event.plain_result("已退出wiki查询~"))
                        controller.stop()
                        return
                    choice_index = int(choice) - 1  # 将用户输入转换为索引
                    if 0 <= choice_index < len(options):
                        logger.info(f"选择选项: {options[choice_index]['title']}")
                        await event.send(
                            event.plain_result(
                                f"你选择了{choice_index + 1}: {options[choice_index]['title']}，请稍后..."
                            )
                        )
                        matched_url = options[choice_index]["url"]
                        output_path = os.path.join(
                            self.gamelist["issac"]["output_dir"],
                            f"{original_query}_{choice_index + 1}.png",
                        )
                        if (
                            not os.path.exists(output_path)
                            or time.time() - os.path.getmtime(output_path)
                            > self.keep_temp_time
                        ):
                            await self.take_full_screenshot(
                                matched_url, output_path, "issac"
                            )
                        await event.send(event.image_result(output_path))
                        controller.stop()
                        return
                    else:
                        logger.info(f"选项超出范围: {event.message_str}")
                        await event.send(
                            event.plain_result(
                                f"选项超出范围。请输入1到{len(options)}之间的数字。"
                            )
                        )
                        return
                except ValueError:  # 处理非数字输入
                    logger.warning(f"用户输入非数字: {event.message_str}")
                    await event.send(
                        event.plain_result(
                            "无效输入。请输入一个阿拉伯数字作为选项序号。"
                        )
                    )
                    return

            try:
                await empty_mention_waiter(event)
            except TimeoutError:
                logger.warning("用户操作超时。")
                await event.send(event.plain_result("已退出wiki查询，操作超时"))
            except Exception as e:
                logger.error(f"处理用户选择时出错: {str(e)}", exc_info=True)
            finally:
                event.stop_event()
        except Exception as e:
            logger.error(f"处理以撒消歧义页面失败: {str(e)}", exc_info=True)
            return None

    async def take_full_screenshot(
        self, url: str, output_path: str, game: str = None, delay: int = 10
    ) -> bool:
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
            logger.info(f"开始截图: {url}")
            driver = self.driver
            driver.get(url)
            initial_height = 0
            scroll_segments = 5  # 将页面分成 5 段滚动
            scroll_pause_time = 0.75  # 每段滑动后等待0.75秒，可根据需要调整

            for i in range(scroll_segments):  # 分段滚动
                driver.execute_script(
                    f"window.scrollTo(0, document.body.scrollHeight / {scroll_segments} * ({i + 1}));"
                )
                await asyncio.sleep(scroll_pause_time)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height > initial_height:
                    initial_height = new_height
                if i == scroll_segments - 1:
                    driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                    await asyncio.sleep(
                        scroll_pause_time
                    )  # 确保最终完全滚动到底部并等待
            if game == "issac":
                if "分类:消歧义页" in driver.page_source:
                    element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                "//a[@title='分类:消歧义页' and text()='消歧义页']",
                            )
                        )
                    )
                    last_height = element.location["y"] + 300
                else:
                    element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "mw-normal-catlinks"))
                    )
                    last_height = element.location["y"]

            elif game == "sr" or game == "ys":
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                await asyncio.sleep(scroll_pause_time)  # 等待页面加载完成
                element = (
                    driver.find_elements(By.CSS_SELECTOR, "div.a_section.c_0.c_3")[-1]
                    if game == "sr"
                    else driver.find_elements(
                        By.CSS_SELECTOR, "div.a_section.shows.shows_3"
                    )[-1]
                )
                last_height = (
                    element.location["y"] + element.size["height"] + 500
                )  # 适配sr/ys页面
            elif game == "zzz" or game == "ww":
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                await asyncio.sleep(scroll_pause_time)  # 等待页面加载完成
                element = driver.find_elements(
                    By.CSS_SELECTOR,
                    "div.flex.flex-col.justify-center.text-sm.font-light.text-gray-400.border-opacity-20",
                )[-1]
                last_height = (
                    element.location["y"] + element.size["height"]
                )  # 适配zzz/ww页面
            elif game == "fz":
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                await asyncio.sleep(scroll_pause_time)  # 等待页面加载完成
                element = driver.find_elements(By.ID, "footer-poweredbyico")[-1]
                last_height = (
                    element.location["y"] + element.size["height"]
                )  # 适配fz页面
            else:
                last_height = driver.execute_script("return document.body.scrollHeight")
            logger.info(f"页面最终总高度: {last_height}px")
            driver.set_window_size(1920, last_height)
            driver.execute_script("window.scrollTo(0, 0);")
            driver.save_screenshot(output_path)
            logger.info(f"截图成功保存到: {output_path}")
            return True
        except Exception as e:
            logger.error(f"截图失败: {str(e)}", exc_info=True)
            return False

    @filter.command("getscreenshot")
    async def getscreenshot_handler(self, event: AstrMessageEvent, url: str):
        """输入 getscreenshot [URL] 获取网页截图"""
        output_path = os.path.join(self.assets_dir, "temp_screenshot.png")
        success = await self.take_full_screenshot(url=url, output_path=output_path)
        if success:
            yield event.image_result(output_path)
        else:
            yield event.plain_result("截图失败，请检查URL是否正确")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        logger.info("退出driver...")
        self.driver.quit()

    @filter.command("infohelp", alias={"gameinfo帮助"})
    async def help_handler(self, event: AstrMessageEvent):
        """获取帮助"""
        help_path = os.path.join(self.assets_dir, "help.png")
        yield event.image_result(help_path)
