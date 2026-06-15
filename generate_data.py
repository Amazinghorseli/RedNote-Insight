"""
generate_data.py - 通用小红书笔记数据生成器
=============================================
生成带 YAML frontmatter + 结构化评论分析的模拟笔记。
任何人都可以用它为自己关注的品类生成 demo 数据。

用法：
  # 默认：生成 6 品类 42 篇（内置演示数据）
  python generate_data.py

  # 自定义品类：生成 30 篇智能马桶笔记
  python generate_data.py --category "智能马桶" --brands "恒洁,九牧,TOTO" --count 30

  # 自定义品类 + 指定输出目录
  python generate_data.py --category "蓝牙耳机" --brands "小米,华为,漫步者" --count 20 --output-dir ./data/raw

  # 保持随机种子（结果可复现）
  python generate_data.py --category "台灯" --brands "欧普,松下,飞利浦" --seed 42
"""
import os
import sys
import random
import argparse
from typing import List, Tuple

# ============================================================
# 模板池 — 品类无关，通过 {category} / {brand} 参数化
# ============================================================

TITLE_TEMPLATES = [
    # --- 测评类 ---
    "{category}到底买哪个？我把全网爆款都买了回来测评",
    "{category}横评！热门品牌真实使用对比",
    "别再乱买了！{category}选购指南来了",
    "{category}红黑榜！这些值得买这些快跑",
    "吐血整理！{category}全网最全测评",
    # --- 种草类 ---
    "再也不怕了！这款{category}真香",
    "跟风买的{category}，结果被全家夸了一星期",
    "{category}太绝了！后悔没早买",
    "有了这个{category}，幸福感直接拉满",
    "姐妹们冲！这款{category}真的太香了",
    # --- 避雷类 ---
    "{category}是智商税吗？用了三个月说点真话",
    "{category}避坑指南！这些千万别买",
    "买错N个{category}后的血泪教训",
    "{category}翻车现场 这些坑千万别踩",
    "别冲动！先看完这篇{category}避雷帖",
    # --- 好物推荐 ---
    "学生党进！平价{category}推荐",
    "无限回购的{category}好物分享",
    "拼多多{category}真香！价格只要一半",
    "均价不到50！这些{category}闭眼入",
    "租房党必看！性价比超高的{category}",
    # --- 开箱类 ---
    "开箱！期待很久的{category}终于到了",
    "被问了800遍的{category}！今天统一回复",
    "颜值暴击！这个{category}美到我尖叫",
    # --- 场景类 ---
    "{category}到底怎么选？看完这篇不踩雷",
    "抄作业！我把全网的{category}攻略都整理好了",
    "后悔没早知道！{category}这样买省一半钱",
]

# 内容结构池 — 每个结构是一个格式化函数，返回内容文本
def _content_review(category: str, brand1: str, brand2: str, brand3: str) -> str:
    p1, p2, p3 = random.randint(3, 5), random.randint(3, 5), random.randint(2, 4)
    pr1, pr2, pr3 = random.randint(30, 200), random.randint(50, 300), random.randint(15, 100)
    return (
        f"花了半个月把小红书推荐的{category}都买回来了！\n\n"
        f"测评结果：\n\n"
        f"1 {brand1} {pr1}元\n"
        f"推荐指数：{'⭐' * p1} {'⭐' * (5-p1)}\n"
        f"品质：{'⭐' * p1}  性价比：{'⭐' * (random.randint(3,5))}\n\n"
        f"2 {brand2} {pr2}元\n"
        f"推荐指数：{'⭐' * p2}\n"
        f"品质：{'⭐' * p2}  性价比：{'⭐' * (random.randint(3,5))}\n\n"
        f"3 {brand3} {pr3}元\n"
        f"推荐指数：{'⭐' * p3}\n"
        f"品质：{'⭐' * p3}  性价比：{'⭐' * (random.randint(3,5))}\n\n"
        f"综合推荐：预算够选{brand1}，性价比选{brand2}，入门选{brand3}！"
    )

def _content_experience(category: str, brand1: str, brand2: str, brand3: str) -> str:
    return (
        f"用了一段时间来说说真实感受。\n\n"
        f"好的地方：\n"
        f"- {category}确实方便，后悔没早点买\n"
        f"- 品质比想象中好，对得起价格\n"
        f"- 颜值在线，朋友来都问\n\n"
        f"不好的地方：\n"
        f"- 没有宣传的那么完美，一些小细节还有提升空间\n"
        f"- 价格偏高，建议活动时入手\n\n"
        f"总结：是提升幸福感的好物，但别期待太完美。"
    )

def _content_price_compare(category: str, brand1: str, brand2: str, brand3: str) -> str:
    return (
        f"发现了一个宝藏！同样的{category}价格竟然差这么多！\n\n"
        f"我的战利品：\n\n"
        f"1 {brand1} 线下门店 {random.randint(100, 500)}元\n"
        f"2 {brand2} 网购 {random.randint(50, 200)}元\n"
        f"3 {brand3} 拼多多 {random.randint(20, 100)}元\n\n"
        f"其实品质差不多，价格差了好几倍！\n"
        f"缺点就是要自己甄别，买到假货就亏了。\n"
        f"但挑对了真的省很多！"
    )

def _content_unboxing(category: str, brand1: str, brand2: str, brand3: str) -> str:
    return (
        f"姐妹们！期待了好久的{category}终于到了！\n\n"
        f"开箱第一印象：\n"
        f"包装：{'精致' if random.random() > 0.3 else '简约'}，自用送人都合适\n"
        f"质感：比想象中{'好' if random.random() > 0.3 else '轻'}，手感不错\n"
        f"颜色：选了最经典的配色，百搭耐看\n\n"
        f"使用初体验：\n"
        f"操作简单，不用看说明书就会用\n"
        f"效果符合预期，没有失望\n\n"
        f"之后再出详细的使用报告！先分享到这～"
    )

def _content_room_makeover(category: str, brand1: str, brand2: str, brand3: str) -> str:
    return (
        f"改造前后对比太大了！\n\n"
        f"改造清单：\n\n"
        f"{brand1} {category} {random.randint(30, 100)}元 — 品质担当\n"
        f"{brand2} {category} {random.randint(20, 80)}元 — 性价比之选\n"
        f"{brand3} 配件 {random.randint(10, 40)}元 — 点睛之笔\n\n"
        f"改造完整个空间的感觉完全不一样了！\n"
        f"朋友来家里都说像换了个房子～"
    )

def _content_student(category: str, brand1: str, brand2: str, brand3: str) -> str:
    return (
        f"学生党看过来！找到了一些超适合宿舍的{category}！\n\n"
        f"推荐清单（总花费不到{random.randint(50, 150)}元）：\n\n"
        f"1 {brand1} {random.randint(20, 60)}元 — 入门够用\n"
        f"2 {brand2} {random.randint(30, 80)}元 — 品质升级\n"
        f"3 {brand3} {random.randint(10, 30)}元 — 宿舍专用\n\n"
        f"室友都说我是全宿舍最会买的！\n"
        f"宿舍生活也要有品质感呀～"
    )

CONTENT_TEMPLATES = [
    _content_review,
    _content_experience,
    _content_price_compare,
    _content_unboxing,
    _content_room_makeover,
    _content_student,
]

# 评论模板池
HIGH_FREQ_WORDS_POOL = [
    ["求链接", "好用吗", "什么牌子", "多少钱", "收藏了"],
    ["好物分享", "爱了爱了", "已下单", "质量好吗", "太实用了"],
    ["推荐", "种草了", "马上买", "靠谱吗", "什么价格"],
    ["比想象中好", "颜值高", "物超所值", "有优惠吗", "哪家店"],
]

COMPLAINTS_POOL = [
    ["价格有点贵", "性价比一般"],
    ["用了一段时间就坏了", "质量不稳定"],
    ["和图片有色差", "实物没那么好看"],
    ["续航/效果没宣传的好", "有点失望"],
    ["尺寸比想象中小", "不够用"],
    ["包装简陋", "不太适合送礼"],
]

PURCHASE_INTENT_POOL = [
    ["值得入手吗", "性价比怎么样"],
    ["什么时候有优惠", "最近有活动吗"],
    ["适合新手/学生党吗", "操作难不难"],
    ["和某某比哪个好", "哪个型号值得买"],
    ["能退换吗", "售后怎么样"],
    ["送人合适吗", "什么颜色好看"],
]

COMPARISON_POOL = [
    ["比某知名品牌便宜很多"],
    ["比同价位其他产品性价比高"],
    ["比实体店便宜一半"],
    ["比网上其他推荐实用多了"],
    ["比大牌质量差不了多少"],
]

BRAND_PREFIXES = [
    "精选", "优选", "品质", "简约", "温馨",
    "时尚", "潮流", "北欧", "日式", "轻奢",
    "创意", "智能", "环保", "天然", "匠心",
]
BRAND_SUFFIXES = [
    "生活", "家居", "好物", "优选", "良品",
    "工坊", "集物", "馆", "小屋", "研究所",
    "馆", "工坊", "小店", "优选", "日记",
]

# ============================================================
# 生成器
# ============================================================

class NoteGenerator:
    """根据品类和品牌列表生成批量笔记"""

    def __init__(self, category: str, brands: List[str], seed: int = None):
        self.category = category
        self.brands = brands
        if seed is not None:
            random.seed(seed)

    def generate(self, count: int) -> List[Tuple]:
        """生成 N 条笔记元组，格式与内置 PRODUCTS 一致"""
        notes = []
        for i in range(count):
            note = self._make_one(i)
            notes.append(note)
        return notes

    def _make_one(self, idx: int) -> Tuple:
        brand = random.choice(self.brands)
        # 模拟多品牌测评场景：取1-3个品牌
        other_brands = [b for b in self.brands if b != brand]
        random.shuffle(other_brands)
        brands_for_review = [brand] + other_brands[:2]
        while len(brands_for_review) < 3:
            brands_for_review.append(f"白牌{random.randint(1, 9)}")
        b1, b2, b3 = brands_for_review[:3]

        # 随机选标题模板 + 填充
        title = random.choice(TITLE_TEMPLATES).format(category=self.category)
        # 避免同一批次标题重复
        if random.random() < 0.15:
            title = title.replace(self.category, f"这款{self.category[:2]}")

        # 随机选内容模板 + 填充
        content_fn = random.choice(CONTENT_TEMPLATES)
        content = content_fn(self.category, b1, b2, b3)

        # 随机选评论数据
        high_freq = random.choice(HIGH_FREQ_WORDS_POOL)
        complaints = random.choice(COMPLAINTS_POOL)
        purchase_intent = random.choice(PURCHASE_INTENT_POOL)
        comparisons = random.choice(COMPARISON_POOL)
        # 品牌相关评论
        related_brands = list(set(brands_for_review[:2] + [random.choice(self.brands)]))
        if brand and brand not in related_brands:
            related_brands.append(brand)

        likes = random.randint(100, 700)
        filename = f"{self._slugify(self.category)}_{idx+1:02d}"
        return (filename, title, self.category, brand, content,
                high_freq, complaints, purchase_intent, comparisons, related_brands, likes)

    @staticmethod
    def _slugify(text: str) -> str:
        """中文品类名转文件前缀：'智能马桶' -> 'zhinengmatong'"""
        import unicodedata
        # 简单拼音化：取每个汉字拼音首字母片段
        # 这里用 transliterate 替代方案：取前两个字符 + hash
        # 更简单：直接取品类前两个汉字
        return text[:2]


# ============================================================
# 内置演示数据（原 42 篇，保持向后兼容）
# ============================================================

BUILTIN_PRODUCTS = [
    # --- 磁吸感应灯 (8篇) ---
    ("cixi_01", "再也不怕黑了！磁吸感应灯真香",
     "磁吸感应灯", "星月灯饰",
     "租房党必备！这个磁吸感应灯真的太绝了\n\n"
     "免打孔磁吸安装，租房党友好\n三档色温可调：暖光/白光/混合\n"
     "人体感应 + 光感，人来就亮\nType-C 充电，续航约20天\n\n"
     "我贴在衣柜下面和床边，晚上起夜再也不摸黑了！\n"
     "奶呼呼的造型真的很治愈～",
     ["求链接", "多少钱", "续航", "暖光好看", "已经下单了"],
     ["续航太短了", "充一次电只能用两周", "磁吸不够紧会掉"],
     ["质量怎么样", "小卧室够用吗", "有优惠吗"],
     ["比宜家的便宜多了", "比欧普的好看"],
     ["星月灯饰", "欧普照明"], 182),

    ("cixi_02", "租房独居女孩的夜间仪式感 百元氛围灯",
     "磁吸感应灯", "几光",
     "谁懂啊！晚上回家有这样的灯光真的会幸福到哭\n\n"
     "最近入了这个几光的感应灯，其实就是想给玄关添点氛围感。\n"
     "没想到装上之后整个家的感觉都不一样了！\n\n"
     "推荐理由：安装超简单，磁吸铁片一贴就上\n"
     "感应灵敏：人来自动亮，人走自动灭\n续航给力：用了半个月还没充过电\n\n"
     "强烈建议独居女孩都安排上！",
     ["好看", "求链接", "多少钱", "安装方便", "推荐"],
     ["价格小贵", "要是再便宜点就好了"],
     ["亮度怎么样", "质感和图片一样吗"],
     ["比名创优品的有质感", "比宜家产品线丰富"],
     ["几光", "名创优品"], 245),

    ("cixi_03", "拼多多30块的磁吸灯居然这么好用？",
     "磁吸感应灯", "拼多多白牌",
     "被小红书姐妹种草的，去拼多多搜同款才30块！\n\n"
     "说实话本来没抱太大期望，结果收到真的惊了\n\n"
     "使用感受：亮度够用，看书玩手机完全OK\n"
     "磁吸稳的，甩都甩不掉\n充电的，不用布线\n\n"
     "缺点就是颜色选择太少了，只有白色。\n"
     "不过这个价格还要啥自行车！冲就完了！",
     ["求链接", "拼多多哪家店", "质量怎么样", "好便宜"],
     ["颜色选择少", "要是粉色就好了", "充电口不是Type-C"],
     ["值得买吗", "容易坏吗"],
     ["比宜家便宜好几倍"],
     ["拼多多白牌"], 312),

    ("cixi_04", "跟风买的磁吸灯，结果被我爸夸了一星期",
     "磁吸感应灯", "德力西",
     "哈哈哈真的没想到！\n\n"
     "给爸妈家装了几个磁吸感应灯在走廊和厨房，\n"
     "我爸用了之后各种发朋友圈炫耀\n\n"
     "我的购买心得：\n"
     "老人起夜安全多了，不用摸黑找开关\n"
     "厨房切菜区装一个，光线无死角\n"
     "安装0门槛，我爸妈自己贴的\n\n"
     "已经给闺蜜家也安排上了！",
     ["求链接", "给爸妈安排", "好用吗", "老人适用"],
     ["亮度一般般", "感应范围有点小"],
     ["厨房能用吗", "防水吗"],
     ["比欧普质量好"],
     ["德力西", "欧普照明"], 156),

    ("cixi_05", "磁吸灯到底买哪个？我把全网爆款都买了回来测评",
     "磁吸感应灯", "综合测评",
     "花了半个月把小红书推的磁吸灯都买回来了！\n\n"
     "测评结果：\n\n"
     "1 星月灯饰 59元\n"
     "续航：4星 色温：5星 颜值：4星\n"
     "2 几光 89元\n"
     "续航：5星 色温：4星 颜值：5星\n"
     "3 拼多多白牌 29元\n"
     "续航：3星 色温：3星 颜值：3星\n\n"
     "综合推荐：星月灯饰性价比最高！\n"
     "不差钱选几光，要便宜选拼多多。",
     ["太实用了", "收藏了", "星月灯饰在哪买", "测评好详细"],
     ["怎么不测续航", "测评不够客观"],
     ["寝室用买哪种", "哪个最亮"],
     ["星月比几光性价比高"],
     ["星月灯饰", "几光", "拼多多白牌"], 567),

    ("cixi_06", "学生党进！20块打造ins风宿舍灯光",
     "磁吸感应灯", "名创优品",
     "宿舍党看过来！只要20块就能让宿舍高级感拉满\n\n"
     "改造清单：\n"
     "磁吸感应灯 x 2：贴在床头和书桌下\n"
     "星星灯串：挂在床帘上\n"
     "氛围蜡烛：muji平替\n\n"
     "室友都问我是不是换宿舍了哈哈哈哈哈！\n"
     "特别是那个磁吸灯，晚上看书超方便，\n"
     "而且不占桌面空间，太适合宿舍党了！",
     ["求链接", "好看", "宿舍能用吗", "不贵"],
     ["不够亮", "充电频率有点高"],
     ["需要打孔吗", "被宿管查吗"],
     ["比muji性价比高"],
     ["名创优品", "muji"], 278),

    ("cixi_07", "磁吸感应灯是智商税吗？用了三个月说点真话",
     "磁吸感应灯", "几光",
     "用了三个月了，说点真实感受。\n\n"
     "好的地方：\n"
     "- 安装确实方便，租房党福音\n"
     "- 晚上起夜真的很实用\n"
     "- 颜值在线，朋友来都问\n\n"
     "不好的地方：\n"
     "- 续航没有宣传的久，实际大概12-15天\n"
     "- 磁吸久了会松动\n"
     "- 价格偏高\n\n"
     "总结：是提升幸福感的小物件，但别期待太完美。",
     ["真实测评", "有用", "准备买"],
     ["续航虚标", "磁吸用久了会掉", "价格偏贵"],
     ["性价比高吗", "和其他品牌比呢"],
     ["比欧普贵但好看"],
     ["几光", "欧普照明", "德力西"], 432),

    ("cixi_08", "姐妹们冲！这家磁吸灯的奶油色太绝了",
     "磁吸感应灯", "奶油家居",
     "啊啊啊这个奶油色的磁吸灯也太好看了吧\n\n"
     "找了很久才找到这种奶乎乎的配色！\n"
     "不是那种死白死白的，是很温柔的奶油白～\n\n"
     "搭配建议：\n"
     "配奶油色系的床头柜，氛围感翻倍\n"
     "暖光模式一开，整个房间都变温柔\n"
     "贴在梳妆镜两侧，化妆光线无敌\n\n"
     "已经被好几个姐妹问链接了哈哈哈！",
     ["好好看", "求链接", "奶油色绝了", "什么牌子"],
     ["只有白色", "想要其他颜色"],
     ["容易脏吗", "耐不耐用"],
     ["比普通白色好看太多"],
     ["奶油家居", "几光"], 389),

    # --- 桌面收纳 (7篇) ---
    ("store_01", "桌面乱成这样？这8个收纳好物拯救你",
     "桌面收纳", "收纳达人",
     "作为一个收纳狂魔，今天把我的桌面收纳秘籍全部分享出来！\n\n"
     "必买清单：\n\n"
     "1 亚克力双层置物架 39元 放护肤品/香水，颜值超高\n\n"
     "2 多层笔筒 15元 旋转设计，拿取超方便\n\n"
     "3 桌面抽屉收纳盒 25元 零碎小物全藏起来\n\n"
     "4 增高架带抽屉 49元 拯救颈椎+收纳两不误\n\n"
     "整理完真的心情都变好了！",
     ["求链接", "亚克力那个好好看", "收纳盒有链接吗"],
     ["积灰不好擦", "亚克力容易刮花"],
     ["尺寸多大", "能放多少东西"],
     ["比无印良品便宜"],
     ["收纳达人", "无印良品"], 421),

    ("store_02", "3块钱的快乐 拼多多收纳盒真香",
     "桌面收纳", "拼多多白牌",
     "你敢信这堆收纳盒加起来不到30块钱？\n\n"
     "推荐这几款我的最爱：\n"
     "桌面小抽屉 3.5元/个 放发圈/小卡子\n"
     "透明收纳盒 5.8元/个 放面膜\n"
     "网格笔筒 4.2元/个 ins风拉满\n\n"
     "全部拼多多买的！姐妹们冲！",
     ["太便宜了", "求店铺", "质量怎么样"],
     ["塑料薄", "有异味", "不够大"],
     ["耐用吗", "会不会退货"],
     ["比名创优品便宜一半"],
     ["拼多多白牌", "名创优品"], 298),

    ("store_03", "被问了800遍的梳妆台收纳！全是干货",
     "桌面收纳", "小雅的梳妆台",
     "每次发梳妆台都被问收纳，今天统一回复！\n\n"
     "我的收纳方案：\n\n"
     "Muji亚克力收纳盒：放口红粉底 199元\n"
     "旋转置物架：放护肤品 45元\n"
     "抽屉分隔板：放小样 19元\n"
     "首饰展示架：放耳环项链 35元\n\n"
     "虽然化妆品多但整齐了真的心情好～",
     ["好整洁", "求链接", "旋转置物架哪买的"],
     ["muji太贵了", "亚克力盒容易脏"],
     ["有平替吗", "防尘吗"],
     ["比tb同款贵但质量好"],
     ["小雅的梳妆台", "muji"], 345),

    ("store_04", "学生党桌面改造 几十块搞定ins风",
     "桌面收纳", "寝室收纳",
     "宿舍桌面太小？那是你不会收纳！\n\n"
     "看看我怎么把80cm小桌面变大的\n\n"
     "增高架：瞬间多出一层空间 29元\n"
     "侧面挂篮：利用垂直空间 15元\n"
     "磁吸置物架：贴在铁皮柜上 23元\n"
     "理线器：线再也不乱了 9.9元\n\n"
     "总花费不到80块，室友都抄作业了！",
     ["爱了", "求增高架链接", "要抄作业"],
     ["桌面太小不够放", "理线器会掉"],
     ["不伤墙面吧", "能放下电脑吗"],
     ["比学校超市便宜太多"],
     ["寝室收纳"], 267),

    ("store_05", "懒人收纳大法！把所有东西都藏起来",
     "桌面收纳", "极简生活",
     "我不配拥有好看的桌面，因为实在太乱了\n\n"
     "直到我发现了一个真理：\n"
     "懒得整理就把所有东西都藏进柜子里！\n\n"
     "推荐这个带抽屉的增高架：\n"
     "上面放显示器\n抽屉里放笔、充电线、耳机\n下面还能塞键盘！\n\n"
     "桌面瞬间变空，心情都舒畅了～",
     ["我需要这个", "求链接", "有宽度要求吗"],
     ["抽屉太浅", "放不了多少东西"],
     ["稳不稳", "什么材质"],
     ["比宜家贝肯特实用"],
     ["极简生活", "宜家"], 198),

    ("store_06", "无限回购的桌面好物！均价不超过50",
     "桌面收纳", "好物分享",
     "整理了一波我无限回购的桌面好物！\n\n"
     "清单：\n"
     "1 可伸缩书架 39元 书多也不怕\n"
     "2 无线充电器收纳座 49元 充电+收纳一体\n"
     "3 磁吸收纳板 29元 小物件上墙\n"
     "4 桌面吸尘器 35元 橡皮屑灰尘全吸走\n\n"
     "每一件都用了一年+，真心推荐！",
     ["无线充电座有意思", "求链接"],
     ["书架积灰", "无线充电太慢"],
     ["吸尘器吸力大吗", "书架稳吗"],
     ["比小米的好看"],
     ["好物分享", "小米"], 215),

    ("store_07", "我妈说：你桌面这么整齐是换人了？",
     "桌面收纳", "收纳小白",
     "作为一个曾经桌面乱到找不到手机的人，\n"
     "现在居然被我妈夸了！\n\n"
     "分享一下我的蜕变过程：\n"
     "第1天：把所有东西清空，擦干净桌面\n"
     "第2天：分类（常用的备用的装饰的）\n"
     "第3天：买收纳盒，每种东西固定位置\n"
     "第7天：养成习惯，用完放回原处\n\n"
     "收纳不是一天的事，但开始了就会爱上！",
     ["好厉害", "求收纳盒推荐", "我也可以试试"],
     ["坚持不下来", "东西太多放不下"],
     ["收纳盒买什么尺寸"],
     [],
     ["收纳小白"], 178),

    # --- 寝室改造 (7篇) ---
    ("dorm_01", "寝室改造后，室友以为我换宿舍了",
     "寝室改造", "改造达人",
     "花了两周时间改造的4人寝！\n\n总花费：436元\n耗时：14天\n\n"
     "改造清单：\n"
     "壁纸贴面 89元 换掉丑丑的柜门\n"
     "床帘 128元 独立空间get\n"
     "地毯 56元 宿舍也有家的感觉\n"
     "桌面增高架 39元 收纳翻倍\n"
     "氛围灯串 35元 晚上超温馨\n"
     "洞洞板 45元 墙上收纳\n"
     "挂篮 44元 省空间\n\n"
     "改完之后真的很不想回家了哈哈哈！",
     ["求链接", "好厉害", "我也要改", "花了多少钱"],
     ["壁纸贴起来很麻烦", "毕业不好还原"],
     ["宿舍允许改造吗", "会被查寝吗"],
     ["比小红书上其他改造贴实用多了"],
     ["改造达人"], 534),

    ("dorm_02", "200块搞定全寝改造！附全部清单",
     "寝室改造", "穷改战士",
     "穷学生改造寝室真的是门学问！\n\n"
     "我花了200块，效果被全宿舍楼围观\n\n"
     "省钱秘籍：\n"
     "壁纸：拼多多买自粘壁纸20元\n桌贴：木纹贴纸15元\n"
     "收纳盒：1688批发的10元/个\n椅垫：记忆棉椅垫25元\n"
     "床帘：淘宝基础款60元\n装饰：海报+干花 30元\n\n"
     "改造完心情真的变超好！学习都更有动力了",
     ["求链接", "好便宜", "壁纸有链接吗"],
     ["自己贴好累", "质量一般"],
     ["查寝会被扣分吗", "能用多久"],
     ["比小红书其他改造便宜一半"],
     ["穷改战士"], 489),

    ("dorm_03", "寝室改造成奶油风 邻居都来参观",
     "寝室改造", "奶油风爱好者",
     "奶油风太适合寝室了吧！暖色调看着就心情好\n\n"
     "色系搭配：\n"
     "主色：奶白色（柜子贴面+床帘）\n"
     "点缀色：浅粉色（装饰+地毯）\n"
     "灯光：暖黄光（绝对不能冷白！）\n\n"
     "最满意的单品：\n"
     "奶油色磁吸灯 氛围担当\n毛绒地毯 幸福感来源\n干花束 拍照出片\n\n"
     "每天回寝室都像回自己小窝一样治愈～",
     ["好温馨", "求全部链接", "奶油色太好看"],
     ["不耐脏", "浅色容易脏"],
     ["改造麻烦吗", "花多少钱"],
     ["比工业风好看一万倍"],
     ["奶油风爱好者"], 423),

    ("dorm_04", "大一新生必看！寝室改造避坑指南",
     "寝室改造", "过来人经验",
     "作为大四老学姐，含泪总结寝室改造的坑！\n\n"
     "不要买：\n1 布艺收纳盒 软塌塌放不了东西\n"
     "2 磁吸挂钩 承重差，掉下来砸到头\n3 地板贴 翘边+难撕\n"
     "4 香薰蜡烛 被宿管没收过\n\n"
     "推荐买：\n1 磁吸感应灯 好用不占地方\n2 洞洞板 收纳神器\n"
     "3 自粘壁纸 便宜好贴\n4 床上桌 冬天不想下床\n\n"
     "新生们看完再买，别交智商税！",
     ["太实用了", "收藏", "学姐好人"],
     ["布艺收纳盒确实垃圾"],
     ["床上桌推荐哪个"],
     [],
     ["过来人经验"], 678),

    ("dorm_05", "室友说我像在宿舍修仙？结果被打脸了",
     "寝室改造", "极简修仙",
     "刚改完室友说我太夸张了，结果一周后全来问我要链接！\n\n"
     "我的极简风改造：\n全白配色 + 一点绿植点缀\n"
     "能上墙的绝不占桌面\n能藏起来的绝不露出来\n\n"
     "最满意的几个单品：\n"
     "洞洞板置物架 墙上收纳\n磁吸灯 无底座不占地\n"
     "桌面增高架 空间翻倍\n鼠标垫超大 当桌垫用\n\n"
     "室友现在天天说看着我的桌面心情好",
     ["好看", "求洞洞板链接", "极简风yyds"],
     ["东西少才好看", "但东西多的人不适合"],
     ["绿植好养吗", "灰尘怎么处理"],
     [],
     ["极简修仙"], 234),

    ("dorm_06", "寝室0元改造！靠的是收纳不是花钱",
     "寝室改造", "免费改造",
     "谁说改造一定要花钱？格局打开！\n\n"
     "0元改造方案：\n重新布局：床和桌子换位置\n"
     "废物利用：快递盒包上好看的纸\n"
     "断舍离：半年没用过的扔掉\n统一色系：把杂乱的包装都撕掉\n\n"
     "甚至用外卖纸袋做了墙面装饰！被夸是全校最会改造的人",
     ["好聪明", "学到了", "我也试试"],
     ["快递盒不够好看", "舍不得扔东西"],
     ["能看看效果图吗"],
     [],
     ["免费改造"], 198),

    ("dorm_07", "宿舍床上桌怎么选？买错3个的血泪教训",
     "寝室改造", "踩坑大王",
     "我在床上桌这条路上花了300元冤枉钱\n\n"
     "踩坑1：夹桌式的 夹不稳，IPAD差点摔了\n"
     "踩坑2：折叠腿的 腿伸不直，难受\n"
     "踩坑3：超大号的 占满整张床\n\n"
     "推荐：可升降桌腿+桌面适中\n价格60-80元左右，脚能伸直，\n"
     "看书看剧都很舒服！\n希望大家别像我一样踩坑",
     ["太真实了", "我也踩过坑", "求推荐链接"],
     ["好的太贵", "便宜的不好用"],
     ["升降的稳吗", "多少尺寸合适"],
     [],
     ["踩坑大王"], 345),

    # --- 香薰/氛围 (6篇) ---
    ("scent_01", "平价香薰蜡烛推荐！几十块get高级感",
     "香薰蜡烛", "香薰爱好者",
     "整理了6款平价又好闻的香薰蜡烛！\n\n"
     "1 名创优品柏林少女平替 35元 玫瑰+荔枝，甜而不腻\n"
     "2 网易严选白茶 49元 很干净的茶香，适合学习\n"
     "3 宜家SINNLIG 39元 红莓+香草，很温暖\n"
     "4 观夏 昆仑煮雪 89元 木质调，高冷高级\n\n"
     "嫌贵的姐妹买名创的就行了！",
     ["求链接", "好闻吗", "名创那个确实好闻"],
     ["燃烧不均匀", "味道太淡了"],
     ["哪个最持久", "哪个适合卧室"],
     ["比祖马龙性价比高"],
     ["香薰爱好者", "名创优品", "宜家", "观夏"], 324),

    ("scent_02", "无火香薰推荐！让房间一直香香的",
     "香薰", "香香女孩",
     "怕蜡烛危险的姐妹看过来！无火香薰才是yyds！\n\n"
     "推荐排名：\n1 宜家DOFTTRA 39元 绿植花香调\n"
     "2 名创优品 29元 价格便宜，味道选择多\n"
     "3 野兽派 129元 好看但贵，送礼合适\n\n"
     "扩香能力：宜家 > 名创 > 野兽派",
     ["宜家那个好闻", "求链接", "能用多久"],
     ["用太快了", "有些味道太冲"],
     ["鼻炎能用吗", "对宠物有害吗"],
     ["比野兽派性价比高"],
     ["香香女孩", "宜家", "名创优品"], 256),

    ("scent_03", "几块钱自制香薰！省钱女孩必学",
     "香薰", "DIY达人",
     "外面卖几十块的香薰，自己做只要几块钱！\n\n"
     "材料清单：精油 5元/瓶（拼多多）\n扩香棒 2元/把（1688）\n"
     "玻璃瓶 3元/个（用过的香水瓶）\n基础油 8元/瓶\n\n"
     "步骤：\n1 基础油 + 精油（10:1）混合\n2 倒入瓶中\n"
     "3 插入扩香棒\n4 完成！\n\n"
     "我做了薰衣草+甜橙的，被夸比名创好闻！",
     ["好厉害", "求教程", "我也要试试"],
     ["留香不够久", "操作麻烦"],
     ["用什么精油好", "能送人吗"],
     ["比买的名创还好闻"],
     ["DIY达人"], 198),

    ("scent_04", "房间香喷喷的秘诀！无限回购的香薰好物",
     "香薰", "香薰大户",
     "一个香薰重度用户的年度爱用！\n\n"
     "蜡烛类：1 宜家SINNLIG 39元 性价比之王\n2 观夏 89元 昆仑煮雪巨高级\n\n"
     "无火类：1 名创优品 29元 便宜随便换\n2 网易严选 49元 白茶的yyds\n\n"
     "喷雾类：1 名创优品 15元 出门前喷一下\n2 宜家 29元 被窝香喷喷\n\n"
     "有香味的房间真的会提升幸福感！",
     ["实用", "收藏了", "宜家那个sinnlig"],
     ["有些用太快了", "蜡烛烧不平"],
     ["哪种最持久", "哪种适合小房间"],
     ["宜家比观夏性价比高"],
     ["香薰大户", "宜家", "观夏", "名创优品"], 287),

    ("scent_05", "名创优品香薰全测评！帮你省钱不踩雷",
     "香薰", "踩雷测评",
     "把所有名创优品的香薰都买回来闻了一遍！\n\n"
     "可以买：\n柏林少女平替 35元 玫瑰味Yyds\n"
     "英国梨平替 35元 很清新的果香\n白茉莉 29元 温柔的茉莉花茶\n\n"
     "不要买：\n蓝色XX 像酒店厕所\n粉色XX 太甜了腻到头晕\n"
     "绿色XX 像男生运动香水\n\n省下来的钱请我喝奶茶谢谢",
     ["太实用了", "柏林少女确实好闻"],
     ["有些测评不客观", "个人喜好不同"],
     ["英国梨和祖马龙像吗"],
     ["和祖马龙比味道"],
     ["踩雷测评", "名创优品"], 567),

    ("scent_06", "无印良品平替！香薰机才30块",
     "香薰机", "平替女孩",
     "姐妹们这个超声波香薰机真的太香了！\n\n"
     "muji无印良品的香薰机要400+，我买的这个才30块！\n\n"
     "容量：200ml 能用6小时\n静音：几乎听不到声音\n"
     "自动断电：水干了自己停\n灯光：7色氛围灯\n\n"
     "加几滴精油，整个房间又香又有氛围感～",
     ["求链接", "好用吗", "真的静音吗"],
     ["喷出来的水雾不大", "容易积水垢"],
     ["耐不耐用", "坏了能退吗"],
     ["比muji便宜十几倍"],
     ["平替女孩", "无印良品"], 432),

    # --- 平价装饰 (7篇) ---
    ("deco_01", "拼多多20元的快乐！房间瞬间变高级",
     "平价装饰", "拼多多女孩",
     "谁说高级感一定要花大钱？拼多多yyds！\n\n"
     "1 仿真绿植 15元 放在书桌上超好看\n2 字母灯牌 18元 晚上开超有氛围\n"
     "3 网格照片墙 12元 记录生活\n4 毛绒地垫 22元 幸福感up\n"
     "5 墙面挂布 9元 遮住丑墙面\n\n全部加起来不到80块！",
     ["求店铺", "好便宜", "仿真绿植哪家"],
     ["仿真绿植塑料感", "挂布显廉价"],
     ["质量怎么样", "味道大吗"],
     ["比宜家便宜好多"],
     ["拼多多女孩", "宜家"], 421),

    ("deco_02", "ins风房间装饰合集！几十块改造出租屋",
     "平价装饰", "出租屋改造",
     "出租屋不要将就！几十块就能住进ins博主家\n\n"
     "棉麻窗帘 45元 换掉丑窗帘\n沙发盖布 35元 遮旧沙发\n"
     "地毯 68元 整个房间质感up\n墙贴画 19元 墙面不空\n"
     "花瓶+干花 25元 角落点缀\n\n房东来看都说改造得好！",
     ["求链接", "窗帘好看", "花瓶有链接吗"],
     ["积灰", "地毯不好清洁"],
     ["房东允许贴墙纸吗"],
     ["比小红书其他出租屋改造实用"],
     ["出租屋改造"], 345),

    ("deco_03", "卧室改造前后对比 只花了150块",
     "平价装饰", "改造对比",
     "150块的卧室改造能做成什么样？\n\n"
     "四件套 59元 换色系就是换风格\n床头罩 25元 遮丑\n"
     "地毯 45元 房间变大\n挂画 19元 氛围感\n花瓶 9元 点睛\n\n"
     "全部淘宝+拼多多买的！改造完睡觉都更香了",
     ["前后差别好大", "求四件套链接"],
     ["拍照光线不一样", "照片看起来比实际好"],
     ["四件套质量好吗", "地毯好打理吗"],
     [],
     ["改造对比"], 567),

    ("deco_04", "卧室氛围感神器！一个灯搞定所有",
     "平价装饰", "氛围感女孩",
     "想要房间有氛围感，最核心的就是灯光！\n\n"
     "主灯：换暖光灯泡 9元\n床头：磁吸感应灯 39元\n"
     "书桌：台灯 35元\n装饰：星星灯串 15元\n\n"
     "灯光一换，整个房间的感觉完全不一样！",
     ["有道理", "求灯泡链接", "什么色温好"],
     ["暖光看书不够亮"],
     ["什么色温适合卧室"],
     [],
     ["氛围感女孩"], 234),

    ("deco_05", "租房党的自我修养！这些装饰房东都夸",
     "平价装饰", "租房达人",
     "租房最怕什么？不让打孔！\n\n"
     "磁吸灯 不用打孔，带走\n伸缩杆窗帘 不用打孔\n"
     "自粘墙纸 撕掉不伤墙\n磁吸置物架 冰箱侧面用\n"
     "可折叠桌椅 搬家方便\n地毯 铺上氛围感拉满\n\n"
     "搬家的时候全都能带走，不浪费！",
     ["实用", "收藏了", "伸缩杆求链接"],
     ["自粘墙纸撕了会留胶", "磁吸的不够稳"],
     ["地毯怎么清洁", "伸缩杆承重够吗"],
     [],
     ["租房达人"], 312),

    ("deco_06", "20块以内！能提升幸福感的10个小物件",
     "平价装饰", "省钱小能手",
     "整理了一波不到20块但能提升幸福感的小东西！\n\n"
     "1 桌面镜子 8元\n2 干花束 12元\n3 数字时钟 15元\n"
     "4 鼠标垫 9元\n5 手机支架 6元\n6 收纳筐 10元\n"
     "7 桌面垃圾桶 5元\n8 冰箱贴 3元\n9 杯垫 5元\n10 钥匙挂 4元\n\n"
     "全部不超过20块！学生党也能冲！",
     ["收藏了", "全部加入购物车"],
     ["太便宜的质量不好", "用不久"],
     ["有链接吗"],
     [],
     ["省钱小能手"], 432),

    ("deco_07", "房间改造翻车现场 这些坑千万别踩",
     "平价装饰", "翻车现场",
     "自以为很懂的开始了房间改造，结果...\n\n"
     "翻车1：地板贴 贴的时候好好的，一周后翘边了\n"
     "翻车2：网红洞洞板 积灰到你怀疑人生\n"
     "翻车3：大面积墙贴 撕的时候墙皮都掉了\n\n"
     "听我一句劝：简单的改造才是最好的！",
     ["太真实了", "地板贴我也踩过坑", "笑死了"],
     ["地板贴确实坑", "洞洞板积灰严重"],
     ["那洞洞板到底买不买"],
     [],
     ["翻车现场"], 678),

    # --- 储物好物 (7篇) ---
    ("box_01", "出租屋收纳看这一篇就够了！空间翻倍秘籍",
     "储物好物", "收纳冠军",
     "住了两年出租屋总结的收纳秘籍！\n\n"
     "【厨房】置物架 49元 台面空间翻倍\n挂杆+挂钩 25元 墙上收纳\n密封罐 15元/套\n\n"
     "【衣柜】压缩袋 19元 冬被体积变1/3\n分层架 29元 利用垂直空间\n"
     "衣架连接扣 9元 叠挂省空间\n\n"
     "【卫生间】免打孔置物架 23元\n磁吸牙刷架 15元\n门背挂钩 12元\n\n"
     "全部加起来不到200！空间大了一倍！",
     ["太专业了", "求链接", "压缩袋推荐哪个"],
     ["免打孔的会掉", "用久了不粘"],
     ["厨房置物架稳吗"],
     ["比muji的收纳方案实用"],
     ["收纳冠军", "muji"], 423),

    ("box_02", "衣柜收纳！换季整理一篇搞定",
     "储物好物", "衣柜整理师",
     "换季了衣柜乱成一团的姐妹看过来！\n\n"
     "Step 1：全部清空，分类\nStep 2：断舍离（一年没穿的捐掉）\n"
     "Step 3：收纳工具\n真空压缩袋 29元\n抽屉分隔板 15元\n"
     "挂袋 19元\n鞋盒 25元/5个\n\n整理完整个人都神清气爽！",
     ["太需要了", "求压缩袋链接", "好整齐"],
     ["整理完又乱了", "坚持不下来"],
     ["真空袋会漏气吗"],
     ["比收纳博主的方法实用"],
     ["衣柜整理师"], 356),

    ("box_03", "厨房收纳好物推荐！租房党必看",
     "储物好物", "厨房达人",
     "租房的厨房一般都很小，收纳就更重要了！\n\n"
     "台面区：双层置物架 45元\n筷子沥水架 15元\n\n"
     "冰箱区：鸡蛋盒 9元\n保鲜盒套装 29元\n\n"
     "水槽区：沥水篮 19元\n挂式垃圾桶 12元\n\n小厨房也能井井有条！",
     ["实用", "求置物架链接", "沥水篮有链接吗"],
     ["台面太小放不下置物架", "沥水篮太小"],
     ["置物架稳吗"],
     [],
     ["厨房达人"], 267),

    ("box_04", "1688批发的收纳盒太香了！价格是淘宝一半",
     "储物好物", "1688女孩",
     "发现了1688这个宝藏！同样的收纳盒价格只有一半！\n\n"
     "1 透明收纳盒 淘宝15 1688只要7元\n"
     "2 抽屉分隔板 淘宝20 1688只要9元\n"
     "3 收纳筐 淘宝25 1688 12元\n"
     "4 化妆品收纳盒 淘宝35 1688 18元\n\n"
     "买了8个盒子总共才花了80块！",
     ["求店铺名", "质量好吗", "1688搜什么关键词"],
     ["运费贵", "要买很多才划算"],
     ["和淘宝质量一样吗"],
     ["比淘宝便宜一半"],
     ["1688女孩"], 312),

    ("box_05", "我家的收纳系统全公开！强迫症极度舒适",
     "储物好物", "强迫症收纳",
     "作为一个强迫症，我的收纳必须整齐划一！\n\n"
     "原则：1 统一容器 2 竖着放 3 贴标签 4 8分满\n\n"
     "标签机 89元\n收纳盒 7元/个\n标签纸 10元/卷\n\n"
     "打开柜子的一瞬间真的极度舒适！",
     ["好整齐", "好治愈", "求标签机链接"],
     ["太费时间了", "普通人坚持不了"],
     ["标签机实用吗", "盒子尺寸怎么选"],
     [],
     ["强迫症收纳"], 389),

    ("box_06", "内衣袜子收纳！10块钱解决乱糟糟",
     "储物好物", "内衣收纳",
     "抽屉里内衣袜子乱成一团的看过来！\n\n"
     "抽屉分隔板 9元 自由组合\n"
     "挂袋式收纳 19元 不占抽屉空间\n\n"
     "整理完抽屉再也不用翻半天找袜子了！",
     ["求链接", "分隔板好实用", "马上买"],
     ["分隔板尺寸不合适", "挂袋太薄"],
     ["能放多少", "什么材质"],
     [],
     ["内衣收纳"], 234),

    ("box_07", "考研党桌面收纳！书多也不怕",
     "储物好物", "考研选手",
     "考研人的桌面永远堆满了书和资料\n\n"
     "可伸缩书架 35元 书立起来省空间\n"
     "桌面增高架 39元 上面放书下面放键盘\n"
     "侧边挂袋 15元 放笔和便利贴\n"
     "旋转笔筒 25元 所有笔一目了然\n"
     "A4文件架 29元 分类存放打印资料\n"
     "抽屉收纳盒 19元 小东西不丢\n\n桌面整齐了，复习效率都高了！",
     ["考研党表示需要", "求链接", "增高架稳吗"],
     ["书太多还是放不下", "桌面不够大"],
     ["伸缩架能放多少书"],
     [],
     ["考研选手"], 456),
]


# ============================================================
# 输出函数
# ============================================================

def generate_comment_section(high_freq, complaints, purchase_intent, comparisons,
                             related_brands, ask_link_count,
                             profit_margin=None, logistics_level=None,
                             competition_level=None, differentiation=None):
    lines = ["<!--"]
    lines.append("comment_analysis:")
    lines.append(f"  high_freq_words: {high_freq}")
    lines.append(f"  complaints: {complaints}")
    lines.append(f"  purchase_intent: {purchase_intent}")
    lines.append(f"  comparison_mentions: {comparisons}")
    lines.append(f"  related_brands: {related_brands}")
    lines.append(f"  ask_link_count: {ask_link_count}")
    if profit_margin is not None:
        lines.append("")
        lines.append("ecommerce:")
        lines.append(f"  profit_margin: {profit_margin}")
        lines.append(f"  logistics_level: \"{logistics_level}\"")
        lines.append(f"  competition_level: \"{competition_level}\"")
        lines.append(f"  entry_difficulty: \"{random.choice(['低', '中', '高'])}\"")
        lines.append(f"  recommended_for_newbie: {random.choice([True, False, True])}")
        lines.append(f"  differentiation_opportunity: \"{differentiation}\"")
        lines.append(f"  estimated_monthly_sales: {random.randint(300, 8000)}")
    lines.append("-->")
    return "\n".join(lines)


def generate_frontmatter(title, product_type, brand, likes, comments_count,
                         price=None, cost=None, weight=None, size=None,
                         category_type=None, return_rate=None):
    date = f"2025-{random.randint(1,5):02d}-{random.randint(1,28):02d}"
    tags = [product_type[:3] + "好物", brand, "小红书爆款"]
    lines = [
        "---",
        f'title: "{title}"',
        f'author: "小红书用户{random.randint(1000,9999)}"',
        f"likes: {likes}",
        f"comments: {comments_count}",
        f"date: {date}",
        f'brand: "{brand}"',
        f"tags: {tags}",
    ]
    # 电商选品核心字段
    if price is not None:
        lines.append(f"price: {price}")
    if cost is not None:
        lines.append(f"cost: {cost}")
    if weight is not None:
        lines.append(f"weight: {weight}")
    if size is not None:
        lines.append(f'size: "{size}"')
    if category_type is not None:
        lines.append(f'category_type: "{category_type}"')
    if return_rate is not None:
        lines.append(f"return_rate: {return_rate}")
    lines.append("---\n")
    return "\n".join(lines)


def generate_note(filename, title, product_type, brand, content,
                  high_freq, complaints, purchase_intent, comparisons,
                  related_brands, likes):
    ask_link_count = int(likes * random.uniform(0.2, 0.5))
    comments_count = int(likes * random.uniform(0.15, 0.35))

    # 🧾 电商选品字段：从品类/品牌推断真实电商数据
    base_cost = random.randint(8, 60)                     # 采购成本
    price = base_cost * random.randint(3, 5)              # 售价 = 成本 × 3~5倍
    weight = round(random.uniform(0.05, 2.0), 2)          # 重量(kg)
    sw, sd, sh = random.randint(5,35), random.randint(5,30), random.randint(3,18)
    size = f"{sw}x{sd}x{sh}cm"
    category_type = "常青款" if random.random() < 0.75 else "季节性"  # 75% 常青
    return_rate = round(random.uniform(0.01, 0.10), 2)    # 退货率 1%-10%

    # 利润率
    profit_margin = round((price - base_cost) / price, 2)
    # 物流友好度（基于重量+尺寸+退货率）
    if weight < 0.3 and sw < 20 and return_rate < 0.05:
        logistics_level = "高"
    elif weight < 1.0 and sw < 30 and return_rate < 0.08:
        logistics_level = "中"
    else:
        logistics_level = "低"
    # 竞争强度
    competition_level = random.choice(["低", "中", "中", "高"])
    # 差异化方向
    differentiation = random.choice([
        "材质升级", "功能组合", "场景细分", "颜色创新",
        "尺寸优化", "配件增加", "包装升级", "套装组合"
    ])

    parts = [
        generate_frontmatter(title, product_type, brand, likes, comments_count,
                            price, base_cost, weight, size,
                            category_type, return_rate),
        content,
        "\n---\n",
        generate_comment_section(high_freq, complaints, purchase_intent,
                                 comparisons, related_brands, ask_link_count,
                                 profit_margin, logistics_level, competition_level,
                                 differentiation),
    ]
    return "".join(parts)


def write_notes(products, output_dir: str):
    """将笔记元组列表写入文件"""
    os.makedirs(output_dir, exist_ok=True)
    count = 0
    for filename, title, product_type, brand, content, hf, cp, pi, cm, rb, likes in products:
        note = generate_note(
            filename, title, product_type, brand,
            content, hf, cp, pi, cm, rb, likes
        )
        filepath = os.path.join(output_dir, f"{filename}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(note)
        print(f"  + {filename}.md | likes={likes:3d} | {title[:25]}")
        count += 1
    return count


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="生成小红书模拟笔记数据（带结构化评论分析）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python generate_data.py
  python generate_data.py --category "智能马桶" --brands "恒洁,九牧,TOTO" --count 30
  python generate_data.py --category "蓝牙耳机" --brands "小米,华为,漫步者" --count 20 --seed 42
        """,
    )
    parser.add_argument("--category", type=str, default=None,
                        help="品类名称，如：智能马桶、蓝牙耳机")
    parser.add_argument("--brands", type=str, default=None,
                        help="品牌列表，逗号分隔，如：恒洁,九牧,TOTO")
    parser.add_argument("--count", type=int, default=20,
                        help="生成笔记数量（默认 20）")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="输出目录（默认 data/raw）")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，设置后结果可复现")

    args = parser.parse_args()

    # 确定输出目录
    project_root = os.path.dirname(os.path.abspath(__file__))
    output_dir = args.output_dir or os.path.join(project_root, "data", "raw")

    if args.category and args.brands:
        # ===== 自定义品类模式 =====
        brand_list = [b.strip() for b in args.brands.split(",") if b.strip()]
        if not brand_list:
            print("[错误] --brands 至少需要一个品牌")
            sys.exit(1)

        if args.seed is not None:
            random.seed(args.seed)

        print(f"[生成] 品类: {args.category}")
        print(f"[生成] 品牌: {', '.join(brand_list)}")
        print(f"[生成] 数量: {args.count} 篇")
        print(f"[生成] 输出: {output_dir}")
        print()

        generator = NoteGenerator(args.category, brand_list, seed=args.seed)
        products = generator.generate(args.count)
        count = write_notes(products, output_dir)
        print(f"\n=> 生成 {count} 篇 {args.category} 笔记 -> {output_dir}")

    else:
        # ===== 默认模式：内置 42 篇 =====
        if args.seed is not None:
            random.seed(args.seed)
        else:
            random.seed(42)

        print(f"[生成] 内置演示数据 6 品类 42 篇")
        print(f"[生成] 输出: {output_dir}")
        print()

        count = write_notes(BUILTIN_PRODUCTS, output_dir)
        print(f"\n=> 生成 {count} 篇演示笔记 -> {output_dir}")
        print("提示: 使用 --category/--brands 参数生成自定义品类数据")


if __name__ == "__main__":
    main()
