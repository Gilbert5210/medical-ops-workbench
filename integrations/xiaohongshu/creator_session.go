package xiaohongshu

import (
    "encoding/json"
    "net/url"
    "regexp"
    "strings"
    "time"

    "github.com/go-rod/rod"
    "github.com/pkg/errors"
    "github.com/xpzouying/xiaohongshu-mcp/humanize"
)

const (
    urlOfCreatorHome = `https://creator.xiaohongshu.com/?source=official`
    creatorSessionTimeout = 20 * time.Second
)

// Confirm an authenticated creator page. New creator pages no longer set
// galaxy_creator_session_id; its absence must not invalidate a working login.
func ensureCreatorSession(page *rod.Page) error {
    if err := page.Navigate(urlOfCreatorHome); err != nil {
        return errors.Wrap(err, "打开创作者中心失败")
    }
    deadline := time.Now().Add(creatorSessionTimeout)
    for time.Now().Before(deadline) {
        if hasCreatorSession(page) {
            humanize.Delay(page.GetContext(), humanize.AfterNavigate)
            return nil
        }
        time.Sleep(500 * time.Millisecond)
    }
    return errors.New("创作者中心登录失效，请重新扫码登录")
}

type creatorIdentity struct {
    URL string `json:"url"`
    Name string `json:"name"`
    Account string `json:"account"`
}

var creatorAccountPattern = regexp.MustCompile(`小红书账号\s*[:：]\s*\S+`)

func creatorSessionReady(identity creatorIdentity) bool {
    u, err := url.Parse(identity.URL)
    return err == nil && u.Scheme == "https" && u.Hostname() == "creator.xiaohongshu.com" &&
        !strings.Contains(u.Path, "login") && strings.TrimSpace(identity.Name) != "" &&
        creatorAccountPattern.MatchString(identity.Account)
}

func hasCreatorSession(page *rod.Page) bool {
    res, err := page.Eval(`() => JSON.stringify({
        url: location.href,
        name: document.querySelector('.user-info .name-box')?.textContent || '',
        account: Array.from(document.querySelectorAll('.description-text')).map(e => e.textContent).join(' ')
    })`)
    if err != nil { return false }
    var identity creatorIdentity
    if json.Unmarshal([]byte(res.Value.String()), &identity) != nil { return false }
    return creatorSessionReady(identity)
}

// CheckCreatorSession is read-only and never opens the upload flow.
func CheckCreatorSession(page *rod.Page) error { return ensureCreatorSession(page) }
