class ProcessBase:
    def __init__(self, params):
        self.params = params
        self.results = {}

    def setup(self):
        """准备阶段：初始化设备、准备资源"""
        pass

    def run(self):
        """执行阶段：控制设备、收集数据"""
        pass

    def cleanup(self):
        """清理阶段：释放资源、关闭设备"""
        pass

    def execute(self):
        """执行完整流程"""
        self.setup()
        self.run()
        self.cleanup()
        return self.get_results()

    def get_results(self):
        """获取结果"""
        return self.results
