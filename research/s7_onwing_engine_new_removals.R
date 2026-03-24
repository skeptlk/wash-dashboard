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
library(tidyr)

config_list <- read.ini( 
  './config/config.ini',
  encoding = getOption("encoding")
)

pool <- dbPool(
  drv = dbDriver("PostgreSQL"),
  dbname = config_list$PROJECT_DB_ECM_NEW$dbname,
  host =  config_list$PROJECT_DB_ECM_NEW$host,
  port = config_list$PROJECT_DB_ECM_NEW$port,
  user = config_list$PROJECT_DB_ECM_NEW$user,
  password = config_list$PROJECT_DB_ECM_NEW$psw
)

onwing_engine <- pool %>% tbl(in_schema("s7_mdb", "onwing_engine")) %>% collect()

onwing_engine_new_removal <- onwing_engine[
  onwing_engine$aircraft_id == "03446" &
  onwing_engine$engine_id == "699539",
]

onwing_engine_new_removal$removal_datetime <- as.POSIXct('2023-10-30 11:26:00')

dbWriteTable(
  pool,
  c("s7_mdb", "onwing_engine"),
  value = onwing_engine_new_removal,
  row.names = FALSE,
  append = TRUE
)

