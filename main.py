from dataclasses import dataclass

import telegram as tm
import requests
import configparser
import bs4
import logging
import sqlite3

from typing import List


@dataclass
class ParseLogic:
    step_type: str
    tag_name: str = None
    tag_class: str = None
    tag_id: str = None


@dataclass
class BlogInfo:
    db_id: int
    name: str
    main_url: str
    notif_text: str
    parse_logics: List[ParseLogic]


class PersoNotifBot:
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0"

    def __init__(self, chat_id, bot_token, database):
        self.logger = logging.getLogger("PersoNotifBot")
        self.chat_id = chat_id
        self.bot_token = bot_token
        self.db_conn = sqlite3.connect(database)
        self.db_curs = self.db_conn.cursor()

    def __del__(self):
        self.db_conn.close()

    def send_perso_notif(self):
        for blog in self._get_blogs_from_db():
            latest_article = self._get_last_article_link(blog)
            if latest_article is not None and self._check_if_article_is_new(blog, latest_article):
                self._send_notif_for_new_article(blog, latest_article)
                self._save_article_link(blog, latest_article)

    def _get_blogs_from_db(self):
        blogs = []

        db_blogs = self.db_curs.execute("SELECT * FROM blogs").fetchall()
        for db_blog in db_blogs:
            (db_id, name, main_url, notif_text, _) = db_blog
            blogs.append(BlogInfo(db_id, name, main_url, notif_text, self._get_parse_logic_for_blog(db_id)))

        return blogs

    def _get_parse_logic_for_blog(self, blog_id: int):
        parse_logics = []

        db_parse_logics = self.db_curs.execute("SELECT * FROM parse_logic WHERE blog_id = ? ORDER BY step_idx",
                                               (blog_id,)).fetchall()
        for db_parse_logic in db_parse_logics:
            (_, _, step_type, tag_name, tag_class, tag_id) = db_parse_logic
            parse_logics.append(ParseLogic(step_type, tag_name, tag_class, tag_id))

        return parse_logics

    def _get_last_article_link(self, blog: BlogInfo):
        try:
            response = requests.get(blog.main_url, headers={"User-Agent": PersoNotifBot.USER_AGENT})
            soup = bs4.BeautifulSoup(response.content, features="html.parser")
            return self._execute_parse_logic(blog.parse_logics, soup)
        except Exception as err:
            self.logger.error(f"Impossible to retrieve latest comic of {blog.name} : {err}")
            return None

    @staticmethod
    def _execute_parse_logic(parse_logics: List[ParseLogic], soup: bs4.BeautifulSoup):
        for parse_logic in parse_logics:
            if parse_logic.step_type == "find":
                soup = soup.find(parse_logic.tag_name, class_=parse_logic.tag_class, id=parse_logic.tag_id)
            elif parse_logic.step_type == "get":
                return soup.get(parse_logic.tag_name)

    def _check_if_article_is_new(self, blog: BlogInfo, article_link: str):
        try:
            old_link = self.db_curs.execute("SELECT last_link FROM blogs WHERE id = ?", (blog.db_id,)).fetchone()[0]
            return old_link != article_link
        except Exception as err:
            self.logger.error(f"Impossible to check if link '{article_link}' is latest article of {blog.name} : {err}")
            return True

    def _save_article_link(self, blog: BlogInfo, article_link: str):
        try:
            self.db_curs.execute("UPDATE blogs SET last_link = ? WHERE id = ?", (article_link, blog.db_id))
            self.db_conn.commit()
        except Exception as err:
            self.logger.error(f"Impossible to save link '{article_link}' as latest article of {blog.name} : {err}")
            pass

    def _send_notif_for_new_article(self, blog: BlogInfo, new_article: str):
        bot = tm.Bot(token=self.bot_token)
        bot.send_message(chat_id=self.chat_id, text=blog.notif_text.format(name=blog.name, url=new_article))


def main():
    config = configparser.ConfigParser()
    config.read(["config.cfg", "private.config.cfg"])

    chat_id = config.get("CONF", "ChatId")
    bot_token = config.get("CONF", "BotToken")
    database = config.get("CONF", "Database")

    perso_notif_bot = PersoNotifBot(chat_id, bot_token, database)
    perso_notif_bot.send_perso_notif()


if __name__ == "__main__":
    main()
