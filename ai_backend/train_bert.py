from transformers import AutoTokenizer
from transformers import TrainingArguments
from transformers import AutoModelForTokenClassification, Trainer
import numpy as np
from transformers import DataCollatorForTokenClassification
import datasets
import evaluate
import wandb

metric = evaluate.load("seqeval")

model_checkpoint = "roberta-large"
tokenizer = AutoTokenizer.from_pretrained(model_checkpoint, add_prefix_space=True)

ds = datasets.load_from_disk("stutter-ds-2")

# from https://huggingface.co/learn/nlp-course/chapter7/2

def align_labels_with_tokens(labels, word_ids):
    new_labels = []
    current_word = None
    for word_id in word_ids:
        if word_id != current_word:
            # Start of a new word!
            current_word = word_id
            label = -100 if word_id is None else labels[word_id]
            new_labels.append(label)
        elif word_id is None:
            # Special token
            new_labels.append(-100)
        else:
            # Same word as previous token
            label = labels[word_id]
            new_labels.append(label)

    return new_labels

def tokenize_and_align_labels(examples):
    tokenized_inputs = tokenizer(
        examples["tokens"], truncation=True, is_split_into_words=True
    )
    all_labels = examples["labels"]
    new_labels = []
    for i, labels in enumerate(all_labels):
        word_ids = tokenized_inputs.word_ids(i)
        new_labels.append(align_labels_with_tokens(labels, word_ids))

    tokenized_inputs["labels"] = new_labels
    return tokenized_inputs

training_ds = ds.map(tokenize_and_align_labels, batched=True, remove_columns=["tokens"])
new_ds =  (training_ds.train_test_split(test_size=0.1))
data_collator = DataCollatorForTokenClassification(tokenizer=tokenizer)

label_names = ["ok", "bad"]
def compute_metrics(eval_preds):
    logits, labels = eval_preds
    predictions = np.argmax(logits, axis=-1)

    # Remove ignored index (special tokens) and convert to labels
    true_labels = [[label_names[l] for l in label if l != -100] for label in labels]
    true_predictions = [
        [label_names[p] for (p, l) in zip(prediction, label) if l != -100]
        for prediction, label in zip(predictions, labels)
    ]
    all_metrics = metric.compute(predictions=true_predictions, references=true_labels)
    return {
        "precision": all_metrics["overall_precision"],
        "recall": all_metrics["overall_recall"],
        "f1": all_metrics["overall_f1"],
        "accuracy": all_metrics["overall_accuracy"],
    }

id2label = {i: label for i, label in enumerate(label_names)}
label2id = {v: k for k, v in id2label.items()}

model = AutoModelForTokenClassification.from_pretrained(
    model_checkpoint,
    id2label=id2label,
    label2id=label2id,
)

print(model.config.num_labels)

args = TrainingArguments(
    "bert-finetuned",
    evaluation_strategy="epoch",
    save_strategy="epoch",
    learning_rate=2e-5,
    num_train_epochs=10,
    weight_decay=0.01,
    report_to="wandb"
)

trainer = Trainer(
    model=model,
    args=args,
    train_dataset=new_ds["train"],
    eval_dataset=new_ds["test"],
    data_collator=data_collator,
    compute_metrics=compute_metrics,
    tokenizer=tokenizer,
)
trainer.train()
trainer.save_model()
