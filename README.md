# Mosaic-Piece-together-your-life
\
******
\
\
我的gemini key: GOOGLE_KEY (付费版)
\
Dayflow的链接: [Dayflow](https://github.com/JerryZLiu/Dayflow)
\
\
我的文件命名方式: test文件都是零时的，正式版不会保留，并且每个test文件都serve as one single purpose
\
\
***捕获***
\
\
screenshots: 存储截图文件夹(归档方式按照 年-月-日)
\
screenshots_test: 测试文件夹
\
template: 当日截图分析的输出模板(具体例子参考timeline_y-m-d.json)【y-m-d指年-月-日，比如2026-01-17】
\
random_screenshots: 用于生成screenshots_test文件夹，通过读取screenshots【当日】现有文件
\
test_screenshots: 截图function
\
test_timeline: 生成timeline的json文件(json文件会生成在对应screenshots文件夹的当日文件夹里面)
\
\
***生成***
\
\
daily_report_y-m-d.json: 每日报告的例子(默认存储路径在对应的screenshots里面)
\
redraw_y-m-d_style.jpg: Gemini3生成的照片去描述这一天。style指绘画风格，目前设置了7种风格[风格设置位置(32-33行)](test_generation.py#L32-L33)
\


## TODO

- [ ] 多个屏幕的判断(用主屏幕做为数据输入？)
- [ ] 讨论合适停止截图时间(我计划是7-23点【默认】，用户可以手动调整接收报告的时间)
- [ ] 关联移动端+其他应用(日历/todo list等)
- [ ] 封装+UI