package main

import (
    "net/http"
    "github.com/gin-gonic/gin"
    "github.com/xpzouying/xiaohongshu-mcp/xiaohongshu"
)

func (s *AppServer) workbenchCreatorStatus(c *gin.Context) {
    b := newBrowser()
    defer b.Close()
    page := b.NewPage()
    defer page.Close()
    if err := xiaohongshu.CheckCreatorSession(page); err != nil {
        respondError(c, http.StatusUnauthorized, "CREATOR_LOGIN_REQUIRED", "发布后台暂不可用", err.Error())
        return
    }
    c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{"is_logged_in": true, "message": "创作者后台连接正常，可以发布。"}})
}
