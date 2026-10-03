Add-Type -AssemblyName System.Speech
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$guion = @(
  "Cada dia se publican en Espana cientos de contratos publicos. Millones de euros en juego. Y la mayoria de las empresas pequenas no se entera de ninguno. Te voy a ensenar un agente que los lee por ellas. Y te voy a ensenar por que no funciono.",
  "Cuatrocientas setenta y cuatro licitaciones nuevas cada dia. Para saber si tu empresa puede presentarse a una, hay que abrir su pliego. Un PDF de decenas de paginas. Y encontrar la clausula que dice que te exigen. Nadie tiene tiempo para eso.",
  "Paso uno: el filtro barato. No abre ni un solo PDF. Lee el anuncio y lo compara con lo que hace la empresa. Van veinte licitaciones en cada pregunta al modelo: cuatro centimos por cada cien. Y atencion a esto: la duda pasa adelante. Nada se descarta en silencio.",
  "Paso dos. Este pliego tiene setenta y siete paginas. Se las damos todas a la inteligencia artificial? No. Costaria veinte veces mas. Un programa sin modelo puntua cada pagina buscando las palabras que importan, encuentra el ancla en la pagina cincuenta y dos, y lee cuatro. El cinco por ciento del documento.",
  "Y aqui esta la parte importante. Al modelo no se le pregunta si la empresa puede presentarse. Se le pide una sola cosa: que copie el requisito, con la frase exacta y el numero de pagina. Despues, un programa busca esa frase, caracter a caracter, en esa pagina. Si no aparece, el requisito se cae. El modelo copia. El programa comprueba que copio.",
  "Paso cuatro: decidir. Y no decide el modelo. Decide un fichero de reglas de cincuenta lineas que cualquiera puede leer. Limitado a proposito: lo unico que puede descartar una licitacion es el volumen de negocios, porque es lo unico que de verdad son dos numeros. Todo lo demas manda a revisar.",
  "Y ahora la parte que nadie ensena. Lo medimos. Cincuenta y dos contratos que cinco empresas ganaron de verdad. El radar encuentra el sesenta y nueve coma dos por ciento. Y un filtro simple por codigo de actividad? El ochenta y dos coma siete. La tesis queda refutada. Perdio.",
  "Pero sabemos por que. Los dieciseis contratos que se escaparon son productos que el perfil de la empresa no nombraba. Una distribuidora de Autodesk que tambien vendia licencias de Adobe. El agente razono bien sobre una descripcion incompleta. El techo no es el modelo: es lo poco que sabe de la empresa.",
  "El criterio de exito estaba escrito y subido al repositorio antes de mirar un solo dato. Por eso este resultado vale algo. Un resultado negativo medido bien vale mas que uno bueno sin medir."
)
for ($i = 0; $i -lt $guion.Length; $i++) {
  $voz = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $voz.SelectVoice("Microsoft Helena Desktop")
  $voz.Rate = 1
  $ruta = Join-Path $dir ("voz_{0:d2}.wav" -f $i)
  $voz.SetOutputToWaveFile($ruta)
  $voz.Speak($guion[$i])
  $voz.Dispose()
  "$ruta"
}
