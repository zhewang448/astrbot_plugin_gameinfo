import time
import os
import asyncio
import json
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.utils.session_waiter import session_waiter, SessionController
import astrbot.api.message_components as Comp
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.api import logger
from thefuzz import fuzz, process
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
    "astrbot_plugin_gameinfo", "bushikq", "一个获取部分二游角色wiki信息的插件", "1.2.3"
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
                "name": "明日方舟",
                "url": "https://prts.wiki/w",
                "output_dir": os.path.join(self.assets_dir, "fzassets"),
                "url_type": "append",  # url + "/" + character
            },
            "ys": {
                "name": "原神",
                "url": "https://gi20.hakush.in/character",
                "output_dir": os.path.join(self.assets_dir, "ysassets"),
                "url_type": "search",  # 需要在列表页搜索
                "xpath_template": "//a[contains(@href, '/character/') and .//div[contains(text(), '{}')]]",
            },
            "sr": {
                "name": "崩坏：星穹铁道",
                "url": "https://hsr20.hakush.in/char",
                "output_dir": os.path.join(self.assets_dir, "srassets"),
                "url_type": "search",
                "xpath_template": "//a[contains(@href, '/char/') and .//div[contains(text(), '{}')]]",
            },
            "zzz": {
                "name": "绝区零",
                "url": "https://zzz3.hakush.in/character",
                "output_dir": os.path.join(self.assets_dir, "zzzassets"),
                "url_type": "search",
                "xpath_template": "//a[contains(@href, '/character/') and .//div[contains(text(), '{}')]]",
            },
            "ww": {
                "name": "鸣潮",
                "url": "https://ww2.hakush.in/character",
                "output_dir": os.path.join(self.assets_dir, "wwassets"),
                "url_type": "search",
                "xpath_template": "//a[contains(@href, '/character/') and .//div[contains(text(), '{}')]]",
            },
            "issac": {
                "name": "以撒的结合：重生",
                "url": "https://isaac.huijiwiki.com/wiki",
                "output_dir": os.path.join(self.assets_dir, "issacassets"),
                "url_type": "append",  # url + "/" + character
            },
            "endfield": {
                "name": "终末地",
                "url": "https://warfarin.wiki/cn/operators",
                "output_dir": os.path.join(self.assets_dir, "endfieldassets"),
                "url_type": "search",
                "xpath_template": "//a[contains(@href, '/cn/operators/') and .//span[contains(text(), '{}')]]",
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
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            # 只有 Chromium 家族才有 experimental option，做个防守式判断
            if hasattr(options, "add_experimental_option"):
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
            yield event.plain_result("还不支持该游戏喵")
        yield event.plain_result(
            f"正在查询 {self.gamelist[game]['name']} 中的 {character} 词条，请稍后..."
        )
        output_dir = self.gamelist[game]["output_dir"]
        os.makedirs(output_dir, exist_ok=True)
        # 获取URL和实际匹配的角色名（用于正确的缓存路径）
        url_result = await self.get_url(game=game, character=character, event=event)
        if url_result == "no_need_to_return_url":  # 无需返回url，停止
            return
        if not url_result:
            yield event.plain_result("url获取失败")
            return
        url, matched_character = url_result
        output_path = os.path.join(output_dir, f"{matched_character}.png")

        # 如果发生了模糊匹配，提示用户
        if matched_character != character:
            yield event.plain_result(
                f"未找到 '{character}'，已自动匹配为 '{matched_character}'"
            )

        if os.path.exists(output_path):
            if (
                time.time() - os.path.getmtime(output_path) < self.keep_temp_time
            ):  # 1小时缓存
                yield event.image_result(output_path)
                return
            else:
                os.remove(output_path)  # 缓存过期，删除旧的截图
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

    @filter.command("endfieldinfo", alias={"终末地wiki查询"})
    async def endfield_handler(self, event: AstrMessageEvent, character: str = None):
        """输入 endfieldinfo [角色名]    返回角色信息截图"""
        async for ret in self.game_info_handler(
            event=event, game="endfield", character=character
        ):
            yield ret

    async def get_url(self, game: str, character: str, event: AstrMessageEvent):
        """
        获取角色详情页URL

        Returns:
            tuple: (url, matched_character) 或 None
        """
        if not self.driver:
            logger.error("浏览器驱动未初始化")
            self._handle_driver_manager()
        if not self.driver:
            logger.error("浏览器驱动初始化失败")
            return None
        if game not in self.gamelist:
            return None

        game_config = self.gamelist[game]
        url_type = game_config.get("url_type", "append")

        # 需要在列表页搜索的游戏
        if url_type == "search":
            try:
                logger.info(f"开始尝试获取url: {character}")
                driver = self.driver
                driver.get(game_config["url"])

                # 从配置中获取 XPath 模板并填充角色名
                xpath_template = game_config.get("xpath_template", "")
                character_link_xpath = xpath_template.format(character.split("/")[0])

                # 等待角色链接加载并可点击
                character_link = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, character_link_xpath))
                )
                url = character_link.get_attribute("href")
                logger.info(f"获取到url: {url}")
                return (url, character)  # 返回URL和实际匹配的角色名
            except Exception as e:
                logger.error(f"精确匹配失败: {str(e)}，尝试模糊匹配")
                # 模糊匹配：自动选择相似度最高的角色
                best_match = await self._fuzzy_match(game, character)
                if best_match:
                    logger.info(
                        f"模糊匹配成功: {character} -> {best_match[0]} (相似度: {best_match[1]}%)"
                    )
                    # 使用最佳匹配重新获取URL
                    result = await self.get_url(game, best_match[0], event)
                    if result:
                        url, _ = result
                        return (url, best_match[0])  # 返回URL和模糊匹配的角色名
                return False

        # 直接拼接 URL 的游戏
        elif url_type == "append":
            if game == "issac":
                base_url = game_config["url"]
                driver = self.driver
                query_url = f"{base_url}/{character}"
                driver.get(query_url)
                if "这是一个消歧义页" in driver.page_source:
                    logger.info(f"检测到以撒消歧义页面: {query_url}")
                    await self._handle_disambiguation_page(
                        original_query=character, query_url=query_url, event=event
                    )
                    return ("no_need_to_return_url", character)
                else:
                    return (query_url, character)
            else:
                return (f"{game_config['url']}/{character}", character)

        return None

    async def _fuzzy_match(self, game: str, character: str) -> tuple[str, int] | None:
        """
        模糊匹配角色名，自动选择相似度最高的结果

        Args:
            game: 游戏标识
            character: 用户输入的角色名

        Returns:
            (最佳匹配角色名, 相似度) 或 None
        """
        try:
            role_list = await self._get_role_list(game)
            if not role_list:
                return None

            # 使用 thefuzz 进行模糊匹配，获取最佳结果
            result = process.extractOne(character, role_list, scorer=fuzz.ratio)
            if result and result[1] >= 60:  # 相似度 >= 60% 才接受
                return result
            return None
        except Exception as e:
            logger.error(f"模糊匹配失败: {str(e)}")
            return None

    async def _get_role_list(self, game: str) -> list[str]:
        """获取游戏角色列表（从缓存或网页抓取）"""
        cache_file = self.data_dir / f"{game}_roles.json"

        # 尝试从缓存读取
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"读取角色列表缓存失败: {e}")

        # 从网页抓取角色列表
        if not self.driver:
            self._handle_driver_manager()
        if not self.driver:
            return []

        try:
            driver = self.driver
            driver.get(self.gamelist[game]["url"])
            await asyncio.sleep(2)  # 等待页面加载

            # 根据游戏类型提取角色名
            role_list = []
            if game in ["ys", "sr", "zzz", "ww"]:
                # 从 div 元素中提取角色名
                elements = driver.find_elements(
                    By.XPATH,
                    "//a[contains(@href, '/character/') or contains(@href, '/char/')]//div[contains(@class, 'name') or contains(@class, 'text')]",
                )
                for elem in elements:
                    text = elem.text.strip()
                    if text and len(text) < 20:  # 过滤掉非角色名的长文本
                        role_list.append(text)
            elif game == "endfield":
                # 从 span 元素中提取角色名
                elements = driver.find_elements(
                    By.XPATH, "//a[contains(@href, '/cn/operators/')]//span"
                )
                for elem in elements:
                    text = elem.text.strip()
                    if text and len(text) < 20 and text not in role_list:
                        role_list.append(text)

            # 去重
            role_list = list(dict.fromkeys(role_list))

            # 保存到缓存
            if role_list:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(role_list, f, ensure_ascii=False, indent=2)
                    logger.info(
                        f"已更新 {game} 角色列表缓存，共 {len(role_list)} 个角色"
                    )
                except Exception as e:
                    logger.warning(f"保存角色列表缓存失败: {e}")

            return role_list
        except Exception as e:
            logger.error(f"抓取角色列表失败: {str(e)}")
            return []

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
            # 保留逻辑，以备不时之需
            # elif game == "sr" or game == "ys":
            #     driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            #     await asyncio.sleep(scroll_pause_time)  # 等待页面加载完成
            #     element = (
            #         driver.find_elements(By.CSS_SELECTOR, "div.a_section.c_0.c_3")[-1]
            #         if game == "sr"
            #         else driver.find_elements(
            #             By.CSS_SELECTOR, "div.a_section.shows.shows_3"
            #         )[-1]
            #     )
            #     last_height = (
            #         element.location["y"] + element.size["height"] + 500
            #     )  # 适配sr/ys页面
            elif game in ["zzz", "ww", "sr", "ys"]:
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

            else:  # 终末地和其他默认逻辑
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
