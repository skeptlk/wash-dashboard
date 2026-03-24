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

parameters <- pool %>% 
  tbl(in_schema("ecmapp", "parameters")) %>% 
  collect()

parameters_oil <- parameters[parameters$flight_phase == "Oil consumption",]

parameters_oil <- parameters_oil[c(1,7,13,24,25),]

parameters_oil$table_name <- "flightinfo_input"

parameters_oil$alias <- "FLTDES"

parameters_oil$parameter_name <- "FLTDES"

parameters_oil$param_description <- "flight description"

# dbWriteTable(
#   pool,
#   c("ecmapp", "parameters"),
#   value = parameters_oil,
#   row.names = FALSE,
#   append = TRUE
# )


