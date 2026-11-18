package xiaohongshu

import "testing"

func TestCreatorSessionReadyWithoutLegacyCookie(t *testing.T) {
    good := creatorIdentity{URL: "https://creator.xiaohongshu.com/new/home", Name: "测试账号", Account: "小红书账号: 123456789"}
    if !creatorSessionReady(good) { t.Fatal("working authenticated page must not require a legacy cookie") }
    for _, item := range []creatorIdentity{
        {URL: good.URL, Name: "", Account: good.Account},
        {URL: good.URL, Name: good.Name, Account: ""},
        {URL: "https://creator.xiaohongshu.com/login", Name: good.Name, Account: good.Account},
        {URL: "https://example.com/new/home", Name: good.Name, Account: good.Account},
        {URL: "https://creator.xiaohongshu.com/new/home", Name: good.Name, Account: "小红书账号:"},
    } {
        if creatorSessionReady(item) { t.Fatalf("unauthenticated page accepted: %+v", item) }
    }
}
