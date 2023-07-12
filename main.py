from fastapi import FastAPI
import pandas as pd
from pydantic import BaseModel
import warnings
from datetime import timedelta

# Define o modo de filtragem de warnings para "ignore"
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", message=".*If you are loading a serialized model.*")


# uvicorn main:app --reload


app = FastAPI()

# Defining information receiving structure
class TransactionData(BaseModel):
    transaction_id: int
    merchant_id: int
    user_id: int
    card_number: str
    transaction_date: str
    transaction_amount: float
    device_id: int

# Creating an empty DataFrame to store transactions
historico = pd.DataFrame(columns=['transaction_id', 'merchant_id', 'user_id', 'card_number',
                           'transaction_date', 'transaction_amount', 'device_id'])


# Defining the post function
@app.post('/modelo')
def previsao_modelo(transaction: TransactionData):
    global historico

    # Create a dictionary with the current transaction data
    data = {
        'transaction_id': [transaction.transaction_id],
        'merchant_id': [transaction.merchant_id],
        'user_id': [transaction.user_id],
        'card_number': [transaction.card_number],
        'transaction_date': [transaction.transaction_date],
        'transaction_amount': [transaction.transaction_amount],
        'device_id': [transaction.device_id],
    }

    # Add the current transaction to the DataFrame
    ultima_entrada_dados = pd.DataFrame(data, index=[0])
    historico = pd.concat([historico, ultima_entrada_dados], ignore_index=True)

    
    # Setting reject flag
    deve_ser_rejeitada = False

    # Elaborating a specific dataframe with all the transactions of the last user_id that performed the transaction
    investigacao_cliente = historico.loc[historico['user_id'] == ultima_entrada_dados.iloc[0]['user_id']]
    investigacao_cliente.sort_values(by = 'transaction_date')
    investigacao_cliente.reset_index(inplace = True, drop = True )
    investigacao_cliente['transaction_date'] = pd.to_datetime(investigacao_cliente['transaction_date'])

    ## Reject transaction if a user is trying too many transactions in a row
    maximo_de_transacoes_seguidas = 3
    maximo_duracao = timedelta(hours=0.5) 

    mensagem_frequencia = 'A frequência de transação está dentro do previsto'
    if len(investigacao_cliente) >= maximo_de_transacoes_seguidas:
        
        # Loop through transactions
        for i in range(len(investigacao_cliente) - maximo_de_transacoes_seguidas + 1):
            # Select the transactions in a row
            transacoes_seguidas = investigacao_cliente.iloc[i:i+maximo_de_transacoes_seguidas]
            
            # Calcula a duração entre a primeira e a última transação
            duracao = transacoes_seguidas.iloc[-1]['transaction_date'] - transacoes_seguidas.iloc[0]['transaction_date']
            
            # Check if the duration is less than or equal to the established limit
            if duracao <= maximo_duracao:
                mensagem_frequencia = "Comportamento suspeito: 3 ou mais transações seguidas em um período menor de 30 minutos"
                deve_ser_rejeitada = True
                break
        else:
           mensagem_frequencia = "Este cliente tem 3 ou mais transações não suspeitas"

    ## Reject transaction if above a threshold
    mensagem_amount = 'Valor de transação dentro do estabelecido'
    maximo_valor_de_transacao = 10000
    if transaction.transaction_amount > maximo_valor_de_transacao:
        mensagem_amount = "Comportamento suspeito: Valor superior ao limite estabelecido"
        deve_ser_rejeitada = True


    ## Reject transaction if there is a chargeback in the past
    mensagem_cbk = 'Usuário não possui histórico de chargeback'
    cbk_historico = pd.read_excel('cbk_stats.xlsx')
    try:
        has_cbk = cbk_historico.loc[cbk_historico['user_id'] == ultima_entrada_dados.set_index('user_id').index[0], 'has_cbk'].values[0]
        if has_cbk:
            mensagem_cbk = 'Usuário possui histórico de chargeback'
            deve_ser_rejeitada = True
    except:
        pass

    
    # Receiving the Machine Learning Model
    modelo = pd.read_pickle('modelo_treinado.pkl')   
    # Let's pass a copy of the original information to our dataset that will be treated 
    dados = ultima_entrada_dados.copy() 

    # Redoing all the modifications that were made to the model
    dados['transaction_date'] = pd.to_datetime(dados['transaction_date'])
    dados['dia'] = dados['transaction_date'].dt.day
    dados['mês'] = dados['transaction_date'].dt.month
    dados['dia_semana'] = dados['transaction_date'].dt.dayofweek
    dados['horario'] = dados['transaction_date'].dt.time
    dados['horario'] = dados['transaction_date'].dt.hour * 3600 + dados['transaction_date'].dt.minute * 60 + dados['transaction_date'].dt.second
    dados.drop(columns = 'transaction_date', inplace = True)
    dados['card_number'] = dados['card_number'].str.replace('*', '')
    dados['card_number'] = pd.to_numeric(dados['card_number'])
    dados.drop(columns = 'device_id', inplace = True)

    ## Reject transaction if there is model not approve
    mensagem_modelo = 'A transação está aprovada pelo nosso modelo de crédito'
    if modelo.predict(dados)[0] == 1:
        mensagem_modelo = 'A transação está rejeitada pelo nosso modelo de crédito'

    ## Reject transaction if any anti-fraud feature is enabled
    mensagem_final = 'A transação está aprovada'
    if deve_ser_rejeitada or modelo.predict(dados)[0] == 1:
        mensagem_final = 'A transação deve ser rejeitada'
    else:
        pass
    
    
    return {print('A "transaction_id":{}'.format(transaction.transaction_id)),
            print(mensagem_frequencia),
            print(mensagem_amount),
            print(mensagem_cbk),
            print(mensagem_modelo),
            print(mensagem_final)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
