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

df_e <- calchist$df[!is.na(calchist$df$maint_datetime),]

df_e$maint_date <- as.Date(df_e$maint_datetime)

df_e <- df_e[with(df_e , order(maint_datetime)),]

df_e$id_wash <- 1:nrow(df_e)

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

onStop(function() {
  poolClose(pool)
})

aircrafts_names <- pool %>%
  tbl(in_schema("s7", "_aircrafts_names")) %>% 
  filter(
    ac_serial %in% !!unique(df_e$aircraft_id)
  ) %>%
  collect()

ac_utilization <- pool %>% 
  tbl(in_schema("s7", "fake_amos_ac_utilization")) %>% 
  filter(
    ac_registr %in% !!substr(unique(aircrafts_names$ac_reg_new),4,nchar(unique(aircrafts_names$ac_reg_new))),
    departure_datetime >= as.Date('2022-10-01'),
    arrival_datetime <= as.Date('2023-06-01')
  ) %>%
  collect()

ac_utilization <- ac_utilization[with(ac_utilization, order(ac_registr, departure_datetime)),]

ac_utilization$departure_date <- as.Date(ac_utilization$departure_datetime)
ac_utilization$arrival_date <- as.Date(ac_utilization$arrival_datetime)

ac_utilization$departure_arrival <- paste0(ac_utilization$departure, "->", ac_utilization$arrival)

ac_utilization_gr <- ac_utilization %>%
  group_by(
    ac_registr,
    departure_date
    #,arrival_date
  ) %>% 
  summarise(
    fn_numbers = paste0(fn_number, collapse = ","),
    flights = paste0(departure_arrival, collapse = ","),
    departures = paste0(departure, collapse = ","),
    arrivals = paste0(arrival, collapse = ","),
    tah = min(tah),
    tac = min(tac)
  )

df_e <- df_e %>%
  left_join(
    aircrafts_names,
    by = c(
      "aircraft_id" = "ac_serial"
    )
  )

df_e$ac_registr <- substr(df_e$ac_reg_new,4,nchar(df_e$ac_reg_new))

df_e_j <- df_e %>%
  left_join(
    ac_utilization_gr,
    by = c(
      "ac_registr" = "ac_registr",
      "maint_date" = "departure_date"
    )
  )

ac_utilization_gr <- ac_utilization_gr[,c("ac_registr", "departure_date","tah","tac")]

colnames(ac_utilization_gr)[
  colnames(ac_utilization_gr) == "tac"
] <- "tac_loss_of_efficiency"

colnames(ac_utilization_gr)[
  colnames(ac_utilization_gr) == "tah"
  ] <- "tah_loss_of_efficiency"

df_e_j$date_loss_of_efficiency <- as.Date(df_e_j$time_loss_of_efficiency)

df_e_j <- df_e_j %>%
  left_join(
    ac_utilization_gr,
    by = c(
      "ac_registr" = "ac_registr",
      "date_loss_of_efficiency" = "departure_date"
    )
  )


df_e_j$cyc_loss_off_efficiency <- df_e_j$tac_loss_of_efficiency - df_e_j$tac

df_e_j$hrs_loss_off_efficiency <- (df_e_j$tah_loss_of_efficiency - df_e_j$tah)/60
