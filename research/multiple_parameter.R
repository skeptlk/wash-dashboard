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

start <- Sys.time()

calchist <- CalculatorHistory_v2$new()

params <- data.frame(
  parameter_name = c("GWFM","DEGT","EGTHDM"),
  flight_phase = c("CRUISE","CRUISE","TAKEOFF"),
  smooth_window = c(30,30,30),
  number_of_obs_mean = c(15,15,15),
  threshhold = c(0.05,2,2),
  cartoonist = c(-1,-1,1)
)

list_calchist_df <- list()

list_calchist_df_event <- list()

for(i in 1:nrow(params)){
  
  calchist$process_history(
    operator = "s7",
    aircraft_type = "A320-200",#"B737-800",
    min_flight_datetime = as.Date('2022-10-01'),
    max_flight_datetime = as.Date('2023-06-01'),
    ata_code = c("206","207","209"),
    flight_phase = params$flight_phase[i],
    parameter_name = params$parameter_name[i],  #"GWFM", # "DEGT",
    smooth_window = params$smooth_window[i],
    number_of_obs_mean = params$number_of_obs_mean[i],
    threshhold = params$threshhold[i],
    cartoonist = params$cartoonist[i]
  )
  
  list_calchist_df[[as.character(i)]] <- calchist$df
  list_calchist_df_event[[as.character(i)]] <- calchist$df_event
  
}

list_hc <- list()

for(i in 1:length(list_calchist_df)){
  
  df <- list_calchist_df[[as.character(i)]]
  
  engine_id <- unique(list_calchist_df_event[[as.character(1)]]$engine_id)[8]
  maint_datetime <- df$maint_datetime[!is.na(df$maint_datetime) & df$engine_id == engine_id]
  maint_datetime <- maint_datetime[1]
  
  
  list_hc[[i]] <- visualize_by_enginehc_hc_v02(
    df = df,
    engine_id = engine_id,
    maint_datetime = maint_datetime,
    #params[i,],
    enable = NULL #input$cgi_enable,
  )
  
}

hw_grid(
  list_hc,
  rowheight = 740,
  ncol = 1
)

end <- Sys.time()

end - start

View(calchist$df_event[,c(
  "ac_reg_new",
  "engine_position",
  "engine_id",
  "maint_datetime",
  "ata_code",
  "delta_float_value_custom",
  "mean_float_value_custom_before_wash",
  "mean_float_value_custom_after_wash",
  "time_loss_of_efficiency",
  "departures",
  "arrivals",
  #"flights",
  "cyc_loss_off_efficiency",
  "hrs_loss_off_efficiency"
)])
