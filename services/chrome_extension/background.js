// background.js - 只有这里正确，Python 才能收到消息

// 监听 Tab 更新（比如输入新网址）
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === 'complete' && tab.url) {
        console.log("Tab updated:", tab.url);
        sendUrlToPython(tab.url);
    }
});

// 监听 Tab 切换（比如从 Google 切换到 银行页面）
chrome.tabs.onActivated.addListener(activeInfo => {
    chrome.tabs.get(activeInfo.tabId, (tab) => {
        if (tab && tab.url) {
            console.log("Tab activated:", tab.url);
            sendUrlToPython(tab.url);
        }
    });
});

// 发送数据给 Python
function sendUrlToPython(url) {
    // 过滤掉 chrome:// 开头的系统页面
    if (url.startsWith("chrome://")) return;

    fetch("http://localhost:5001/update_url", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ url: url })
    })
    .then(response => console.log("Sent to Python:", response.status))
    .catch(error => console.error("Error sending to Python:", error));
}