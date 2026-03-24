library(DT)
library(shiny)
library(bs4Dash)
library(shinymanager)
library(shinyjs)
library(dbplyr)
library(dplyr) 
library(DBI)
library(pool)
library(RPostgreSQL)
library(ini)
library(shinyWidgets) 
library(shinycssloaders)
library(highcharter)
library(data.table)
library(shinyscreenshot)
library(xts)
library(reactable)
library(sortable)
library(ggplot2)
library(R6)
library(dplyr)
library(data.table)
library(caTools)
library(RPostgreSQL)

library(DT)
library(shiny)
library(bs4Dash)
library(shinymanager)
library(shinyjs)
library(dbplyr)
library(dplyr) 
library(DBI)
library(pool)
library(RPostgreSQL)
library(ini)
library(shinyWidgets) 
library(shinycssloaders)
library(highcharter)
library(data.table)
library(shinyscreenshot)
library(xts)
library(reactable)
library(sortable)

for(lf in list.files('./utils/',full.names = T, recursive = T)){
  source(lf)
}

calchist <- CalculatorHistory$new()

calchist$process_history(
  operator = "s7",
  aircraft_type = "B737-800",
  min_flight_datetime = as.Date('2022-10-01'),
  max_flight_datetime = as.Date('2023-06-01'),
  ata_code = c("206","207","209"),
  flight_phase = "TAKEOFF",
  parameter_name = "EGTHDM"
)

esn <- "658783"

df_esn <- calchist$df[calchist$df$engine_id == esn,]

visualize_by_engine(calchist$df, esn, maint_datetime = NA)

View(df_esn)
