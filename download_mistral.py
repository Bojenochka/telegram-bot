from transformers import AutoTokenizer, AutoModelForCausalLM

# Укажите название модели
model_name = "mistralai/Mistral-7B-Instruct-v0.1"

# Загрузка токенизатора и модели
print("Загружаем токенизатор...")
tokenizer = AutoTokenizer.from_pretrained(model_name)

print("Загружаем модель...")
model = AutoModelForCausalLM.from_pretrained(model_name)

# Сохраните модель локально
model.save_pretrained("./mistral_model")
tokenizer.save_pretrained("./mistral_model")
print("Модель сохранена в папке ./mistral_model")