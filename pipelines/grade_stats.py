import os
from urllib.parse import urlparse

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

url = urlparse(os.environ["DATABASE_URL"])
jdbc = {
    "url": f"jdbc:postgresql://{url.hostname}:{url.port or 5432}{url.path}",
    "user": url.username,
    "password": url.password,
    "driver": "org.postgresql.Driver",
}

spark = (
    SparkSession.builder.appName("scribe-grade-stats")
    .config("spark.jars.packages", "org.postgresql:postgresql:42.7.4")
    .getOrCreate()
)


def table(name):
    return spark.read.format("jdbc").options(dbtable=name, **jdbc).load()


def save(frame, name):
    frame.withColumn("computed_at", F.current_timestamp()).write.format("jdbc").options(
        dbtable=name, truncate="true", **jdbc
    ).mode("overwrite").save()


answers = table("answers").select("answer_id", "question_id")
questions = table("questions").select("question_id", "exam_id", "number")
grades = table("grades").withColumn("mark", F.coalesce("override_marks", "final_marks"))
scored = grades.join(answers, "answer_id").join(questions, "question_id")

question_stats = scored.groupBy("exam_id", "question_id", "number").agg(
    F.count("*").alias("answers"),
    F.avg(F.col("mark") / F.col("max_marks")).cast("double").alias("mean_score"),
    F.stddev("mark").cast("double").alias("stddev"),
    F.avg(F.col("flagged").cast("int")).cast("double").alias("flag_rate"),
)

point_max = table("rubric_points").select("point_id", F.col("marks").alias("point_max"))
judge_totals = (
    table("judgments").join(point_max, "point_id")
    .withColumn("capped", F.greatest(F.lit(0), F.least("marks", "point_max")))
    .groupBy("answer_id", "model").agg(F.sum("capped").alias("judge_total"))
)
gaps = (
    judge_totals.join(grades.select("answer_id", "final_marks"), "answer_id")
    .join(answers, "answer_id").join(questions, "question_id")
    .withColumn("gap", F.abs(F.col("judge_total") - F.col("final_marks")))
)
judge_stats = gaps.groupBy("exam_id", "model").agg(
    F.count("*").alias("answers"),
    F.avg("gap").cast("double").alias("mean_gap"),
    F.avg((F.col("gap") <= 1).cast("int")).cast("double").alias("within_one"),
)

save(question_stats, "question_stats")
save(judge_stats, "judge_stats")
spark.stop()
