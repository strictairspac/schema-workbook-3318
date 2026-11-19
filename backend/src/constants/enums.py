ROLES = ('admin', 'operator', 'viewer')
RUN_STATES = ('queued', 'running', 'completed', 'failed')
# 取证包：排队 -> 执行 -> 待核对 -> 已发布；装不下/失效/失败为终止态
PACKAGE_STATES = ('queued', 'running', 'review', 'published', 'infeasible', 'invalid', 'failed')
