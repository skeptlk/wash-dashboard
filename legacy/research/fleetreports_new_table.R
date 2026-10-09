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

fleetreports_dateend_di <- Sys.Date()
fleetreports_datestart_di <- Sys.Date() - 30

fleetsummary <- pool %>%
  tbl(in_schema("ecmapp", "_fleetsummary")) %>%
  filter(
    operator == "s7",
    aircraft_type == "A320-200"
  ) %>%
  collect()

preset <- pool %>%
  tbl(in_schema("ecmapp", "preset")) %>%
  filter(
    report_name %in% c(
      "ALL TAKE OFF Trends (MAIN)"
    ),
    operator == "s7"
  ) %>%
  collect()

params <- pool %>%
  tbl(in_schema("ecmapp", "engine_raw_output_mv")) %>%
  mutate(
    parameter_name_flight_phase = paste0(
      parameter_name,
      "_",
      flight_phase
    )
  ) %>%
  filter(
    aircraft_id %in% !!unique(fleetsummary$aircraft_id) &
      parameter_name_flight_phase %in% !!unique(
        paste0(
          preset$main_param_name,
          "_",
          preset$main_flght_phs
        )
      ) &
      as.Date(flight_datetime) >= !!fleetreports_datestart_di & 
      as.Date(flight_datetime) <= !!fleetreports_dateend_di
  ) %>%
  collect()

params <- rbind(
  params,
  pool %>%
    tbl(in_schema("ecmapp", "engine_input_mv")) %>%
    mutate(
      parameter_name_flight_phase = paste0(
        parameter_name,
        "_",
        flight_phase
      )
    ) %>%
    filter(
      aircraft_id %in% !!unique(fleetsummary$aircraft_id) &
        parameter_name_flight_phase %in% !!unique(
          paste0(
            preset$main_param_name,
            "_",
            preset$main_flght_phs
          )
        ) &
        as.Date(flight_datetime) >= !!fleetreports_datestart_di & 
        as.Date(flight_datetime) <= !!fleetreports_dateend_di
    ) %>%
    collect()
)

params_aircraft <- pool %>%
  tbl(in_schema("ecmapp", "aircraft_input_mv")) %>%
  mutate(
    parameter_name_flight_phase = paste0(
      parameter_name,
      "_",
      flight_phase
    )
  ) %>%
  filter(
    aircraft_id %in% !!unique(fleetsummary$aircraft_id) &
      parameter_name_flight_phase %in% !!unique(
        paste0(
          preset$main_param_name,
          "_",
          preset$main_flght_phs
        )
      ) &
      as.Date(flight_datetime) >= !!fleetreports_datestart_di & 
      as.Date(flight_datetime) <= !!fleetreports_dateend_di
  ) %>%
  collect()

params_aircraft <- rbind(
  params_aircraft,
  pool %>%
    tbl(in_schema("ecmapp", "aircraft_raw_outpt_mv")) %>%
    mutate(
      parameter_name_flight_phase = paste0(
        parameter_name,
        "_",
        flight_phase
      )
    ) %>%
    filter(
      aircraft_id %in% !!unique(fleetsummary$aircraft_id) &
        parameter_name_flight_phase %in% !!unique(
          paste0(
            preset$main_param_name,
            "_",
            preset$main_flght_phs
          )
        ) &
        as.Date(flight_datetime) >= !!fleetreports_datestart_di & 
        as.Date(flight_datetime) <= !!fleetreports_dateend_di
    ) %>%
    collect()
)

params$float_value[
  !is.na(params$integer_value)
  ] <- params$integer_value[
    !is.na(params$integer_value)
    ]

params_aircraft$float_value[
  !is.na(params_aircraft$integer_value)
  ] <- params_aircraft$integer_value[
    !is.na(params_aircraft$integer_value)
    ]

aircraft <- pool %>%
  tbl(in_schema("ecmapp", "aircraft")) %>%
  filter(
    aircraft_id %in% !!unique(fleetsummary$aircraft_id)
  ) %>%
  collect()

aircraft_names <- pool %>%
  tbl(in_schema("ecmapp", "aircraft_names")) %>%
  filter(
    ac_serial %in% !!unique(fleetsummary$aircraft_id)
  ) %>%
  collect()

engine_config <- pool %>%
  tbl(in_schema("ecmapp", "engine_config")) %>%
  filter(
    engine_id %in% !!unique(fleetsummary$engine_id)
  ) %>%
  collect()

params <- params %>%
  left_join(
    engine_config,
    by = c(
      "engine_id" = "engine_id"
    )
  )

params <- params %>%
  left_join(
    aircraft_names,
    by = c(
      "aircraft_id" = "ac_serial"
    )
  )

params <- params %>%
  left_join(
    aircraft,
    by = c(
      "aircraft_id" = "aircraft_id"
    )
  )

params_aircraft <- params_aircraft %>%
  left_join(
    aircraft_names,
    by = c(
      "aircraft_id" = "ac_serial"
    )
  )

params_aircraft <- params_aircraft %>%
  left_join(
    aircraft,
    by = c(
      "aircraft_id" = "aircraft_id"
    )
  )

params <- params[with(params, order(engine_id, flight_datetime)),]

params_nest_1 <- params[
  params$parameter_name_flight_phase == unique(params$parameter_name_flight_phase)[1],
  c(
    "ac_reg_new","engine_position","engine_id",
    "parameter_name_flight_phase","flight_datetime", "integer_value", "float_value","char_value"
  )] %>% 
  nest(-c(ac_reg_new,engine_position, engine_id))

#,"ac_reg_old", "aircraft_id", "aircraft_type", ,ac_reg_old, aircraft_id, aircraft_type

colnames(params_nest_1)[
  colnames(params_nest_1) == "data"
] <- unique(params$parameter_name_flight_phase)[1]

for(
  parameter_name_flight_phase in unique(params$parameter_name_flight_phase)[
    2:length(unique(params$parameter_name_flight_phase))
  ]
){
  
  params_nest_n <- params[
    params$parameter_name_flight_phase == parameter_name_flight_phase,
    ] %>% 
    nest(-c(ac_reg_new,engine_position, engine_id))  
  
  colnames(params_nest_n)[
    colnames(params_nest_n) == "data"
    ] <- parameter_name_flight_phase
  
  params_nest_1 <- params_nest_1 %>%
    left_join(
      params_nest_n,
      by = c(
        "ac_reg_new" = "ac_reg_new",
        "engine_position" = "engine_position",
        "engine_id" = "engine_id"
      )
    )
  
}

                
create_plot <- function(x){
  
  x$flight_datetime <- datetime_to_timestamp(x$flight_datetime)
  
  hchart(x, "area", hcaes(x = flight_datetime, y = float_value)) %>% 
    hc_title(text = "") %>% 
    hc_yAxis(
      title = list(text = "")
      #title = list(text = "Hits", style = list(color = "white", fontFamily = "Roboto Slab"))
      #,labels = list(style = list(color = "white", fontFamily = "Roboto Slab"))
    ) %>%
    hc_xAxis(
      title = list(text = ""),
      #labels = list(style = list(color = "white", fontFamily = "Roboto Slab")),
      type = 'datetime',
      ordinal = FALSE
    )  %>%
    hc_colors(colors = "#7cb5ec85") %>% # "#F56B38"
    hc_size(height = 250) %>% 
    hc_tooltip(pointFormat = "{point.tooltip}")
}

columns_list <- list(
  ac_reg_new = colDef(
    width = 80,
    sticky = "left",
    style = list(cursor = "pointer"),
    headerStyle = list(cursor = "pointer")
  ),
  engine_position = colDef(
    width = 80,
    sticky = "left",
    style = list(cursor = "pointer"),
    headerStyle = list(cursor = "pointer")
  ), 
  engine_id = colDef(
    width = 80,
    sticky = "left",
    style = list(cursor = "pointer"),
    headerStyle = list(cursor = "pointer")
  )
)

for(parameter_name_flight_phase in unique(params$parameter_name_flight_phase)){
  
  columns_list[[parameter_name_flight_phase]] <- colDef(
    name = parameter_name_flight_phase, 
    minWidth = 500, 
    align = "center",
    cell = function(value){
      if (is.null(value) == F) {
        create_plot(value)
      }
    }
  )
  
}

reactable(
  params_nest_1, 
  filterable = TRUE,
  # searchable = TRUE,
  resizable = TRUE,
  defaultPageSize = 5,
  showPageSizeOptions = T, 
  pageSizeOptions = c(5, 10, 25, 50, 100),
  highlight = T, 
  theme = reactableTheme(
    # backgroundColor = "#1D2024", color = "white", borderColor = "#666666",
    # paginationStyle = list(color = "white"), 
    # selectStyle = list(color = "black"),
    # headerStyle = list(color = "white", fontFamily = "Arial"),
    cellStyle = list(
      #color = "#FAFAFA", 
      fontFamily = "Source Code Pro, Consolas, Monaco, monospace", 
      fontSize = "14px"
    )
  ),
  columns = columns_list
)


