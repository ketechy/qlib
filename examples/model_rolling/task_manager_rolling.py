from pprint import pprint

import fire
import qlib
from qlib.config import REG_CN
from qlib.model.trainer import task_train
from qlib.workflow import R
from qlib.workflow.task.gen import RollingGen, task_generator
from qlib.workflow.task.manage import TaskManager, run_task
from qlib.workflow.task.collect import RecorderCollector
from qlib.workflow.task.ensemble import RollingEnsemble
import pandas as pd
from qlib.workflow.task.utils import list_recorders

data_handler_config = {
    "start_time": "2008-01-01",
    "end_time": "2020-08-01",
    "fit_start_time": "2008-01-01",
    "fit_end_time": "2014-12-31",
    "instruments": "csi100",
}

dataset_config = {
    "class": "DatasetH",
    "module_path": "qlib.data.dataset",
    "kwargs": {
        "handler": {
            "class": "Alpha158",
            "module_path": "qlib.contrib.data.handler",
            "kwargs": data_handler_config,
        },
        "segments": {
            "train": ("2008-01-01", "2014-12-31"),
            "valid": ("2015-01-01", "2016-12-31"),
            "test": ("2017-01-01", "2020-08-01"),
        },
    },
}

record_config = [
    {
        "class": "SignalRecord",
        "module_path": "qlib.workflow.record_temp",
    },
    {
        "class": "SigAnaRecord",
        "module_path": "qlib.workflow.record_temp",
    },
]

# use lgb
task_lgb_config = {
    "model": {
        "class": "LGBModel",
        "module_path": "qlib.contrib.model.gbdt",
    },
    "dataset": dataset_config,
    "record": record_config,
}

# use xgboost
task_xgboost_config = {
    "model": {
        "class": "XGBModel",
        "module_path": "qlib.contrib.model.xgboost",
    },
    "dataset": dataset_config,
    "record": record_config,
}

# Reset all things to the first status, be careful to save important data
def reset(task_pool, exp_name):
    print("========== reset ==========")
    TaskManager(task_pool=task_pool).remove()

    exp, _ = R.get_exp(experiment_name=exp_name)

    for rid in exp.list_recorders():
        exp.delete_recorder(rid)


# This part corresponds to "Task Generating" in the document
def task_generating():

    print("========== task_generating ==========")

    tasks = task_generator(
        tasks=[task_xgboost_config, task_lgb_config],
        generators=RollingGen(step=550, rtype=RollingGen.ROLL_SD),  # generate different date segment
    )

    pprint(tasks)

    return tasks


# This part corresponds to "Task Storing" in the document
def task_storing(tasks, task_pool, exp_name):
    print("========== task_storing ==========")
    tm = TaskManager(task_pool=task_pool)
    tm.create_task(tasks)  # all tasks will be saved to MongoDB


# This part corresponds to "Task Running" in the document
def task_running(task_pool, exp_name):
    print("========== task_running ==========")
    run_task(task_train, task_pool, experiment_name=exp_name)  # all tasks will be trained using "task_train" method


# This part corresponds to "Task Collecting" in the document
def task_collecting(task_pool, exp_name):
    print("========== task_collecting ==========")

    def get_group_key_func(recorder):
        task_config = recorder.load_object("task")
        model_key = task_config["model"]["class"]
        rolling_key = task_config["dataset"]["kwargs"]["segments"]["test"]
        return model_key, model_key, rolling_key

    def my_filter(recorder):
        # only choose the results of "LGBModel"
        model_key, rolling_key = get_group_key_func(recorder)
        if model_key == "LGBModel":
            return True
        return False

    collector = RecorderCollector(exp_name)
    # group tasks by "get_task_key" and filter tasks by "my_filter"
    artifact = collector.collect(RollingEnsemble(), get_group_key_func, rec_filter_func=my_filter)
    print(artifact)


def main(
    provider_uri="~/.qlib/qlib_data/cn_data",
    task_url="mongodb://10.0.0.4:27017/",
    task_db_name="rolling_db",
    exp_name="rolling_exp",
    task_pool="rolling_task",
):
    mongo_conf = {
        "task_url": task_url,
        "task_db_name": task_db_name,
    }
    qlib.init(provider_uri=provider_uri, region=REG_CN, mongo=mongo_conf)

    reset(task_pool, exp_name)
    tasks = task_generating()
    task_storing(tasks, task_pool, exp_name)
    task_running(task_pool, exp_name)
    task_collecting(task_pool, exp_name)


if __name__ == "__main__":
    fire.Fire()
