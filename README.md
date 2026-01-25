# Mosaic-Piece-together-your-life

***仅private repo用于开发和测试！不要把这个repo设置成public！***

我的gemini key: AIzaSyAi8N4Jv8-wCi9iSQDjm8vSe8BVoJhdPyE (付费版)<br>
Dayflow的链接: [Dayflow](https://github.com/JerryZLiu/Dayflow)<br>

# test_fucntions
test文件都是零时的，正式版不会保留，并且每个test文件都serve as one single purpose<br>
### 生成
test_generation: 生成所有用于【网页】的原始数据<br>
### 捕获
screenshots: 存储截图文件夹(归档方式按照 年-月-日)<br>

screenshots_test: 测试文件夹<br>

test_check_app.py: 针对windows监控打开的窗口(不检测后台运行)

test_export_google_info: 合并calendar和tasks并且导出到google_today_y_m_d.json<br>

test_google_calendar: 获取用户当日日历内容(Google的日历是包含todo list的)<br>

test_google_tasks: 获取用户当日todo list<br>

test_random_screenshots: 用于生成screenshots_test文件夹，通过读取screenshots【当日】现有文件<br>

test_screenshots: 截图function(目前为了方便测试是5秒一截屏，正常情况是15min一截屏)<br>

test_timeline: 生成timeline的json文件(json文件会生成在对应screenshots文件夹的当日文件夹里面)<br>

# examples
daily_report_y-m-d.json: 每日报告的例子(默认存储路径在对应的screenshots里面)<br>

example_template: 当日截图分析的输出模板(具体例子参考timeline_y-m-d.json)【y-m-d指年-月-日，比如2026-01-17】<br>

google_today_y_m_d.json: 存储当日来自Google calendar和tasks的数据<br>

redraw_y-m-d_style.jpg: Gemini3生成的照片去描述这一天。style指绘画风格，目前设置了7种风格: [风格设置位置(32-33行)](test_generation.py#L32-L33)，[具体风格prompt位置](test_generation.py#L129-L187)<br>

timeline_y-m-d.json: 最终的文件，也是web读取的数据
# 网页
在terminal运行`python -m http.server 8000`，然后去浏览器输入`http://localhost:8000/web/`，再看右上角的`load`去加载文件。

## TODO

[技术报告link](https://docs.google.com/document/d/1F85HuejYfe3ML9heM1xdtx68Vv-Pm2eYJL_ZSMMWx94/edit?usp=sharing)

- [ ] 正反馈(多种形式鼓励【UI】)(AI生成个人形象) H H
- [ ] 关联其他应用(日历/todo-list) 任意能调用api的日历 P S
- [ ] 隐私问题(本地存储)(识别浏览器网页黑名单) P S
- [ ] 停止截图/接收报告时间【默认7-23】(用户可以手动调整接收报告的时间)(后续: 学习时间) H H
- [ ] 关联移动端(icloud not app)
- [ ] 封装+UI(动画)