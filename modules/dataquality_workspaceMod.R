dataquality_workspaceModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("dataquality_workspace"))
  
}

dataquality_workspaceMod <- function(input, output, session, credentials, headerselectors, pool, id_tab) {
  
  ns <- session$ns
  
  output$dataquality_operator <- renderUI({
    
    ns <- session$ns
    
    fleetsummary <- pool %>% tbl(in_schema("ecmapp", "_fleetsummary")) %>% collect()
    
    userdefault_test <- pool %>%
      tbl(in_schema("utair", "userdefault_test")) %>%
      filter(
        user %in% !!credentials()$user
      ) %>%
      collect()
    
    if(nrow(userdefault_test) == 0){
      
      selected <- unique(fleetsummary$operator)[1]
      
    }
    else{
      
      selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_operator_pi
      
    }
    
    pickerInput(
      ns("dataquality_operator_pi"),
      label = "Operator",
      choices = unique(fleetsummary$operator), # "utair",
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = selected, #"utair",#unique(fleetsummary$operator)[1],
      multiple = F
    )
    
  })
  
  dataquality_data <- reactiveValues(
    sge = NULL,
    mdb = NULL,
    ectm = NULL,
    mail_flightdata = NULL,
    no_data_report = NULL
  )
  
  
  observeEvent(input$update_dataquality_data, {
    browser()
    fleetsummary <- pool %>%
      tbl(in_schema("ecmapp", "_fleetsummary")) %>%
      filter(
        operator %in% !!input$dataquality_operator_pi
      ) %>%
      collect()
    
    fleetsummary <- fleetsummary[!duplicated(fleetsummary),]
    
    aircraft_names <- pool %>%
      tbl(in_schema("ecmapp", "aircraft_names")) %>%
      filter(
        ac_serial %in% !!unique(
          fleetsummary$aircraft_id
        )
      ) %>%
      collect()
    
    aircraft <- pool %>%
      tbl(in_schema("ecmapp", "aircraft")) %>%
      filter(
        aircraft_id %in% !!unique(
          fleetsummary$aircraft_id
        )
      ) %>% 
      collect()
    browser()
    # dataquality_data$no_data_report <- pool %>%
    #   tbl(in_schema("ecmapp", "engine_raw_output")) %>%
    #   filter(
    #     aircraft_id %in% !!unique(
    #       fleetsummary$aircraft_id
    #     )
    #   ) %>%
    #   group_by(
    #     aircraft_id,
    #     flight_phase
    #   ) %>%
    #   summarise(
    #     last_seen_flight_datetime = max(flight_datetime, na.rm = T)
    #   ) %>%
    #   collect()
    
    dataquality_data$no_data_report <- pool %>%
      tbl(in_schema("ecmapp", "no_data_report")) %>%
      filter(
        aircraft_id %in% !!unique(
          fleetsummary$aircraft_id
        )
      ) %>%
      collect()
    
    dataquality_data$no_data_report$days_since_last_point = as.numeric(
      Sys.Date() - as.Date(dataquality_data$no_data_report$last_seen_flight_datetime)
    )
    
    dataquality_data$no_data_report <- dataquality_data$no_data_report %>%
      left_join(
        aircraft_names,
        by = c(
          "aircraft_id" = "ac_serial"
        )
      ) %>%
      left_join(
        aircraft,
        by = c(
          "aircraft_id" = "aircraft_id"
        )
      ) %>%
      select(
        aircraft_type,
        ac_reg_new,
        ac_reg_old,
        aircraft_id,
        flight_phase,
        last_seen_flight_datetime,
        days_since_last_point
      )
    
    dataquality_data$mail_flightdata <- pool %>%
      tbl(in_schema(
        "common", 
        "seen_emails_flight_data"
      )) %>%
      select(
        from,
        sent,
        subject,
        file_name
      ) %>%
      filter(
        !is.na(file_name)
      ) %>%
      collect()

    dataquality_data$mail_flightdata <- dataquality_data$mail_flightdata[
      -grep(
        "@s7.",
        dataquality_data$mail_flightdata$from
      ),]
    browser()
    
    operator <- input$dataquality_operator_pi
    
    if(input$dataquality_operator_pi == "northwest"){
      
      operator <- c(
        operator,
        "@nwt"
      )
      
    }
    
    dataquality_data$mail_flightdata <- dataquality_data$mail_flightdata[
      grep(
        paste(operator,collapse="|"),
        dataquality_data$mail_flightdata$from
      ),]
    
    if(!(input$dataquality_operator_pi %in% c("krasavia", "iraero", "utair", "northwest", "premieravia"))){
      
      dataquality_data$sge <- pool %>%
        tbl(in_schema(
          input$dataquality_operator_pi, 
          "_sge_processed_reports"
        )) %>%
        collect()
      
      dataquality_data$sge$aircraft_id <- sapply(
        strsplit(
          dataquality_data$sge$filename,
          "_"
        ), 
        `[`, 
        1
      )
      
      dataquality_data$sge <- dataquality_data$sge %>%
        left_join(
          aircraft_names,
          by = c(
            "aircraft_id" = "ac_serial"
          )
        )
      
      dataquality_data$mdb <- pool %>%
        tbl(in_schema(
          input$dataquality_operator_pi, 
          "_seen_mdbs"
        )) %>%
        collect()
      
    }
    
    
  })
  
  output$dataquality_email_table <- renderReactable({
    
    req(dataquality_data$mail_flightdata)
    
    if (is.null(dataquality_data$mail_flightdata)){
      return()
    }
    else{
      # browser()
      df <- dataquality_data$mail_flightdata
      
      df$email_date <- as.Date(df$sent)
      
      reactable(
        df,
        searchable = TRUE,
        filterable = TRUE,
        showPageInfo = TRUE,
        showPagination = TRUE,
        
        wrap = FALSE,
        resizable = TRUE,
        striped = TRUE,
        highlight = TRUE,
        groupBy = c(
          "email_date"
          #"sent"
        ),
        columns = list(
          from = colDef(aggregate = "unique"),
          subject = colDef(aggregate = "unique")
        ),
        defaultSorted = list(email_date = "desc"),
        bordered = TRUE
      )
    }
    
  })
  
  output$dataquality_email_plot <- renderHighchart({
    
    req(dataquality_data$mail_flightdata)
    
    if (is.null(dataquality_data$mail_flightdata)){
      return()
    }
    else{
      
      mail_flightdata_group <- dataquality_data$mail_flightdata %>%
        mutate(
          email_date = as.Date(sent)
        ) %>%
        group_by(
          email_date,
          from
          #,subject
        ) %>%
        summarise(
          number_of_files = n()
        )
      
      highchart(type = "stock") %>%
        hc_add_series(
          mail_flightdata_group,
          "column",
          hcaes(
            x = email_date,
            y = number_of_files
            #,color = ac_reg_new
            ,group = from
          ),
          stacking = "normal",
          dataLabels = list(
            enabled = TRUE,
            format='{point.number_of_files}',
            enabled = TRUE,
            verticalAlign = 'top'
          ),
          showInLegend = TRUE
        ) %>%
        hc_legend(
          enabled = TRUE
        ) %>%
        hc_rangeSelector(
          buttons = list(
            list(type = 'all', text = 'All'),
            list(type = 'day', count = 5, text = '5d'),
            list(type = 'day', count = 10, text = '10d'),
            list(type = 'day', count = 15, text = '15d'),
            list(type = 'month', count = 1, text = '1m'),
            list(type = 'month', count = 3, text = '5m')
          ),
          selected = 3
        )
    }
    
  })
  
  output$dataquality_no_data_report <- renderReactable({
    
    
    req(dataquality_data$no_data_report)
    
    if (is.null(dataquality_data$no_data_report)){
      return()
    }
    else{
    
      reactable(
        dataquality_data$no_data_report,
        searchable = TRUE,
        filterable = TRUE,
        showPageInfo = TRUE,
        showPagination = TRUE,
        
        wrap = FALSE,
        resizable = TRUE,
        striped = TRUE,
        highlight = TRUE,
        groupBy = c(
          "aircraft_type"
        ),
        # columns = list(
        #   flight_datetime = colDef(aggregate = "max")
        # ),
        defaultSorted = list(last_seen_flight_datetime = "desc"),
        bordered = TRUE
      ) 
      # %>% 
      #   add_title(
      #     "No data report", 
      #     align = "center"
      #   )
    }
    
  })
  
  output$dataquality_mdb_table <- renderReactable({
    
    req(dataquality_data$mdb)
    
    if (is.null(dataquality_data$mdb)){
      return()
    }
    else{
      
      mdb <- dataquality_data$mdb[,c(
        setdiff(
          colnames(
            dataquality_data$mdb
          ),
          "mdb_etag"
        )
      )]
      
      mdb$process_date <- as.Date(mdb$processed_ts)
      
      # browser()
      
      reactable(
        mdb,
        searchable = TRUE,
        filterable = TRUE,
        showPageInfo = TRUE,
        showPagination = TRUE,
        
        wrap = FALSE,
        resizable = TRUE,
        striped = TRUE,
        highlight = TRUE,
        groupBy = c(
          "process_date"
          #"processed_ts"
        ),
        # columns = list(
        #   flight_datetime = colDef(aggregate = "max")
        # ),
        defaultSorted = list(process_date = "desc"),
        bordered = TRUE
      ) 
      # %>% 
      #   add_title(
      #     "Mdb data quality", 
      #     align = "center"
      #   )
    }
    
  })
  
  output$dataquality_sge_table <- renderReactable({
    
    req(dataquality_data$sge)
    
    if (is.null(dataquality_data$sge)){
      return()
    }
    else{
      
      sge <- dataquality_data$sge[,c(
        "processedts",
        "ac_reg_new",
        "aircraft_id",
        "ac_reg_old",
        "encodername",
        # "flight_phase",
        # "flight_datetime",
        "filename"
      )]
      
      colnames(sge)[colnames(sge) == "encodername"] <- "aircraft_family"
      
      sge$process_date <- as.Date(sge$processedts)
      
      reactable(
        sge,
        searchable = TRUE,
        filterable = TRUE,
        showPageInfo = TRUE,
        showPagination = TRUE,
        
        wrap = FALSE,
        resizable = TRUE,
        striped = TRUE,
        highlight = TRUE,
        groupBy = c(
          "process_date",
          #"processedts",
          "ac_reg_new"
        ),
        # columns = list(
        #   flight_datetime = colDef(aggregate = "max")
        # ),
        defaultSorted = list(process_date = "desc"),
        bordered = TRUE
      ) 
      # %>% 
      #   add_title(
      #     "Sge data quality", 
      #     align = "center"
      #   )
    }
    
  })
  
  output$dataquality_sge_plot <- renderHighchart({
    
    req(dataquality_data$sge)
    
    if (is.null(dataquality_data$sge)){
      return()
    }
    else{
      # browser()
      
      sge_group <- data.frame(
        dataquality_data$sge %>%
          mutate(
            processed_date = as.Date(processedts)
          ) %>%
          group_by(
            processed_date,
            ac_reg_new
          ) %>%
          summarise(
            number_of_sge = n()
          ) %>%
          filter(
            ac_reg_new != "-"
          )
      )
      
      highchart(type = "stock") %>%
        hc_add_series(
          sge_group,
          "column",
          hcaes(
            x = processed_date,
            y = number_of_sge
            #,color = ac_reg_new
            ,group = ac_reg_new
          ),
          stacking = "normal",
          dataLabels = list(
            enabled = TRUE,
            format='{point.number_of_sge}',
            enabled = TRUE,
            verticalAlign = 'top'
          ),
          showInLegend = TRUE
        ) %>%
        hc_legend(
          enabled = TRUE
        ) %>%
        hc_rangeSelector(
          buttons = list(
            list(type = 'all', text = 'All'),
            list(type = 'day', count = 5, text = '5d'),
            list(type = 'day', count = 10, text = '10d'),
            list(type = 'day', count = 15, text = '15d'),
            list(type = 'month', count = 1, text = '1m'),
            list(type = 'month', count = 3, text = '5m')
          ),
          selected = 3
        )
    }
    
  })
  
  output$dataquality_workspace <- renderUI({
    
    fluidRow(
      
      bs4Card(
        width = 12,
        headerBorder = FALSE,
        collapsible = FALSE,
        fluidRow(
          column(
            8,
            fluidRow(
              uiOutput(ns("dataquality_operator"))
            )
            
          ),
          br(),
          column(1),
          column(
            3,
            hr(),
            fluidRow(
              actionBttn(ns("update_dataquality_data"), "Update data")
            )
          )
        )
      ),
      
      bs4TabCard(
        width = 12,
        maximizable = TRUE,
        solidHeader = FALSE,
        sidebar = boxSidebar(),
        tabPanel(
          title = "No data report",
          withSpinner(reactableOutput(ns("dataquality_no_data_report")))
        ),
        tabPanel(
          title = "Sage data",
          div(
            style = 'overflow-y:scroll;height:850px;',
            withSpinner(highchartOutput(ns("dataquality_sge_plot"))),
            hr(),
            # h3("Sge data quality"),
            withSpinner(reactableOutput(ns("dataquality_sge_table"))),
            hr(),
            # h3("Mdb data quality"),
            withSpinner(reactableOutput(ns("dataquality_mdb_table")))
          )
        ),
        tabPanel(
          title = "Mail flight data",
          # withSpinner(highchartOutput(ns("dataquality_email_plot"))),
          # hr(),
          # # h3("Email flight data"),
          # withSpinner(reactableOutput(ns("dataquality_email_table")))
          div(
            style = 'overflow-y:scroll;height:850px;',
            withSpinner(highchartOutput(ns("dataquality_email_plot"))),
            hr(),
            # h3("Email flight data"),
            withSpinner(reactableOutput(ns("dataquality_email_table")))
          )
          
        )
      )
    )
    
  })
  
  # return(reactive({maintenance_data}))
  
}